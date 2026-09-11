import platform
import logging as log
import os

from core.utilities.resolvetypes import resolve_type
from core.external import pyboard
from rich import print

from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup


class MicropythonDevice(AbstractProcessorGroup):

	def __init__(self, name=None, connect=True, port=None, exec_main=False, handshake=False):
		super().__init__(name)
		self.connect_ = connect

		self.device = None
		self.board_name = None
		self.port = None
		self.connected = False
		self.exec_main_ = exec_main
		self.handshake_ = True

	def __getstate__(self):
		return {}
	def __setstate__(self, state):
		pass

	def __del__(self):
		## disconnect() clears self.device once the port is actually closed
		## (see SerialMPDevice.disconnect()) -- this only still fires for a
		## device that was never explicitly disconnected, so the port may
		## genuinely already be gone by the time garbage collection gets
		## here. Best-effort only: there's no one left to report a failure
		## to from inside __del__, so swallow it rather than let Python
		## print a traceback for a cleanup step that was never guaranteed
		## to run at a useful time in the first place.
		if self.device:
			try:
				self.device.exit_raw_repl()
			except Exception:
				pass

	def __call__(self, command):
		raise Exception("Method not defined!")

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.__call__('exec(open("main.py").read())')

	def scan_root(self):
		"""
		Scan the filesystem on the pico device
		"""
		fs = {key:None for key in self.device.fs_listdir(".")}
		return fs

	def exec_cleanup(self, command):
		result = self.__call__(command)
		return result
	
	def readline(self, timeout=15):
		output = self.device.read_until(1, b"\r\n", timeout=timeout)  # Read data with timeout
		if output:
			return output.decode('utf-8')


class SerialMPDevice(MicropythonDevice):
	exclusion_list = []
	def __init__(self, name=None, connect=True, port=None, exec_main=False, handshake=False, search_name=False):
		MicropythonDevice.__init__(self, name=name, connect=connect, port=port, exec_main=False, handshake=False,)

		self.search_name = search_name
		if self.connect_ == "autoconnect":
			self.auto_connect()
			if not self.connected:
				log.error(f"SerialMPDevice construction failed: {name}")

		if self.connected:
			if exec_main:
				self.exec_main()

			if handshake:
				self.handshake()

	# ---------- Serial utilities ------------------
	def all_ports():
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		return [str(port) for port in all_ports]

	def print_all_ports():
		print("All availbale ports:")
		all_ports = SerialMPDevice.all_ports()
		for port in all_ports:
			print(port)
		print("-"*10)

	def potential_ports():
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		all_ports = [str(port) for port in all_ports]
		potential_ports = [port for port in all_ports \
						   if str(port).__contains__("/dev/cu.") \
						   or str(port).__contains__("/dev/ttyACM")]
		return(potential_ports)

	def mount_all():
		"""
		This method mounts all available micropython serial ports and return a list of
		them.
		"""
		all_ports = SerialMPDevice.potential_ports()
		mpdevices = []
		for port in all_ports:
			device = SerialMPDevice(connect=True, port=port)
			if device.is_connected():
				mpdevices.append(device)
		return mpdevices
	
	def connect(self, port):
		try:
			port = port.strip()
			log.debug(f"Attempting connection to — {port}")
			self.device = pyboard.Pyboard(port, 115200)
			self.port = port
			self.connected = True
			log.debug(f"Connected to port: {self.port}")
			self.device.enter_raw_repl()
		except Exception as e:
			log.debug(f"Connection failed - {port}!")
			log.error(e)
			return

		## board.name is informational (used for auto_connect()'s optional
		## search_name matching) -- not defining it is a valid board.py, not
		## a connection failure, so this is its own try/except: the port is
		## connected and usable either way.
		try:
			self.device.exec_("import board")
			self.board_name = self.exec_cleanup("board.name")
			log.debug(f"Board name: {self.board_name}")
		except Exception as e:
			log.debug(f"Could not read board.name on {port}: {e}")
			self.board_name = None

	def disconnect(self):
		self.device.exit_raw_repl()
		self.device.close()
		## Cleared so __del__'s `if self.device:` guard sees nothing left to
		## close -- without this, __del__ still finds the (now-closed)
		## Pyboard object truthy later and tries to exit_raw_repl() a port
		## that's already shut, raising PortNotOpenError at garbage-
		## collection time. This was the actual bug; __del__'s own
		## try/except is only a backstop for a device that was never
		## disconnect()'d at all.
		self.device = None
		if self.port in SerialMPDevice.exclusion_list:
			SerialMPDevice.exclusion_list.remove(self.port)

	def auto_connect(self, port=None):
		"""
		Function tries and connects to the first valid SerialMPDevice it finds.
		"""
		log.info("Attempting micropython autoconnect.")
		if self.port == None:
			if platform.system() == "Linux":
				log.debug("Plateform is Linux.")
				port = '/dev/ttyACM'
			elif platform.system() == "Darwin":
				log.debug("Plateform is Darwin (MacOS).")
				port = '/dev/cu.usbmodem10'
			else:
				log.error("Unsupported plateform (os).")
				
		# Selective port connections based on system scan
		all_ports = list(SerialMPDevice.potential_ports())
		for pport in all_ports:
			port = pport.split(" ")[0]
			if "Board in FS mode" in str(pport) and port not in SerialMPDevice.exclusion_list:
				log.debug(f"Trying out -> {pport.split(' ')[0]}")
				self.connect(port=port)

			if self.connected:
				log.debug(f"{self.name} -connection-on-> {self.port}")
				
				self.device.enter_raw_repl()
				
				if self.search_name != False:
					if self.board_name != self.search_name:
						log.debug('Not the correct deice. Closing.')
						self.disconnect()
					else:
						log.debug("Correct decice found!")
						SerialMPDevice.exclusion_list.append(self.port)
						break
				else:
					break

				
		if not self.connected:
			log.error("No SerialMP device found. Not connected.")
			SerialMPDevice.print_all_ports()
		else:
			return True

	def handshake(self):
		from ..assembly import ScopeAssembly
		scope = ScopeAssembly.current
		try:
			all_pico_devs = self.exec_cleanup("Handshake.obj_list(globals_=globals())")
			for device in all_pico_devs:
				proxy_device = self.emit_proxy(device)
				scope.add_device(device, proxy_device, description="Micropython proxy peripheral.")
		except Exception as e:
			print(e)
			log.error(f"{self.name} handshake failed!")

	# -------------  Serial Utilities -----------------------

	def __call__(self, command):
		log.debug(f"{self.name} << {command}")
		printed =  'print(' + str(command).replace('\'', '\"') + ')'
		ret = self.device.exec_(printed)
		log.debug(f"{self.name} >> {ret.decode()}")
		return resolve_type(ret.decode().strip("\r\nNone").strip("\r\n"))

	## ---------------------------------------------------------------- sync
	SKIP_DIRS = ("__pycache__", ".git", ".idea", ".vscode", "micropython-async")
	SKIP_FILES = (".DS_Store", ".gitignore", ".pyc")

	def fs_makedirs(self, path):
		"""mkdir -p on the device. Returns the directories it created.

		fs_put() opens the destination for writing and nothing more, so writing
		into a directory that does not exist fails with ENOENT. Every parent has
		to exist first -- which is why the commented-out mkdir in the old version
		made this method unable to sync anything but the top level.
		"""
		made = []
		parts = [p for p in str(path).strip("/").split("/") if p and p != "."]
		for i in range(len(parts)):
			d = "/".join(parts[: i + 1])
			try:
				self.device.fs_mkdir(d)
				made.append(d)
			except Exception as err:
				## already there is the normal case; anything else is real
				if "EEXIST" not in str(err) and "exists" not in str(err).lower():
					log.debug(f"mkdir {d}: {err}")
		return made

	def fs_exists(self, path):
		try:
			self.device.fs_stat(path)
			return True
		except Exception:
			return False

	def _sync_one_file(self, local_path, remote_path, sent, skipped, failed,
						skip_unchanged=True, dry_run=False, verbose=True):
		"""
		Copy exactly one file to exactly one destination path, appending to
		the caller's sent/skipped/failed lists. The shared per-file logic
		behind both sync_files()'s directory walk and its single-file
		shortcut -- same skip_unchanged check, same "one bad file doesn't
		abandon the rest" resilience, same reporting, whichever calls it.
		"""
		if skip_unchanged and not dry_run:
			try:
				st = self.device.fs_stat(remote_path)
				if st and st[6] == os.path.getsize(local_path):
					skipped.append(remote_path)
					return
			except Exception:
				pass          ## not there yet, or no stat -- just send it

		if dry_run:
			sent.append(remote_path)
			return
		try:
			self.device.fs_put(local_path, remote_path)
			sent.append(remote_path)
			if verbose:
				print(f"  [green]sent[/] {remote_path}")
		except Exception as err:
			## Keep going. One unwritable file must not abandon the rest
			## of the tree half-copied.
			failed.append((remote_path, str(err)))
			log.error(f"sync failed for {remote_path}: {err}")
			if verbose:
				print(f"  [red]FAILED[/] {remote_path}: {err}")

	def sync_files(self, local_folder, target_folder, skip_unchanged=True,
					dry_run=False, verbose=True):
		"""Copy a local tree onto the device, creating directories as needed --
		or, when local_folder is a single file rather than a directory, copy
		just that one file to target_folder (the exact destination path, not
		a folder to nest it into). Same skip_unchanged/resilience/reporting
		either way, via _sync_one_file() -- this is what a single-file entry
		in sync_what.yaml's include: should go through, rather than a
		hand-rolled fs_put() call with none of this method's guarantees
		(exactly the gap that let an ENOSPC crash the whole launcher process
		uncaught, before this).

		Returns a summary dict; the caller can tell success from failure, which
		the old version could not -- it caught every exception, aborted the whole
		walk on the first one, and printed "Sync completed" regardless.

		skip_unchanged compares size against the device and skips matching files.
		Serial is slow: a full firmware tree is minutes, an incremental sync is
		seconds. dry_run=True lists what would happen and touches nothing.
		"""
		sent, skipped, failed, made = [], [], [], []

		if os.path.isfile(local_folder):
			self._sync_one_file(local_folder, target_folder.strip("/"), sent, skipped, failed,
									skip_unchanged=skip_unchanged, dry_run=dry_run, verbose=verbose)
		else:
			for root, dirs, files in os.walk(local_folder):
				## prune junk in place so os.walk does not descend into it
				dirs[:] = [d for d in dirs if d not in SerialMPDevice.SKIP_DIRS
							and not d.startswith(".")]

				rel = os.path.relpath(root, local_folder)
				if rel == ".":
					remote_root = target_folder.strip("/")
				else:
					remote_root = "/".join([target_folder.strip("/")] +
											rel.replace("\\", "/").split("/"))

				wanted = [f for f in files
							if not f.startswith(".")
							and not f.endswith(".pyc")
							and f not in SerialMPDevice.SKIP_FILES]
				if not wanted:
					continue

				if not dry_run:
					made += self.fs_makedirs(remote_root)

				for file_name in wanted:
					local_path = os.path.join(root, file_name)
					remote_path = f"{remote_root}/{file_name}"
					self._sync_one_file(local_path, remote_path, sent, skipped, failed,
											skip_unchanged=skip_unchanged, dry_run=dry_run, verbose=verbose)

		summary = {"sent": sent, "skipped": skipped, "failed": failed,
					"dirs_created": made, "dry_run": dry_run}
		if verbose:
			head = "[yellow]DRY RUN[/] " if dry_run else ""
			print(f"{head}sync {local_folder} -> {target_folder}: "
					f"{len(sent)} sent, {len(skipped)} unchanged, "
					f"{len(made)} dirs created, "
					f"{'[red]' if failed else ''}{len(failed)} failed"
					f"{'[/]' if failed else ''}")
			if failed:
				print("  [red]The device tree is now incomplete -- fix and re-run.[/]")
		return summary

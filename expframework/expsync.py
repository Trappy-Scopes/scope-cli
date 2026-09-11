from rich import print
import os
import logging as log
import platform
from concurrent.futures import ThreadPoolExecutor
import time
import datetime


from core.uid import uid
from core.permaconfig.config import TrappyConfig  # AI Generated -- Share/User imports removed, no longer used here (see template())
import core.sync as sync

class ExpSync:
	"""
	Synchronises experiment files with a remote server.
	"""
	active = False
	server = None
	share = None
	username = None
	password = None
	destination_fmt = None

	def configure(scopeconfig):
		## `file_server` currently lives under `config:`; the target format
		## is `Experiment.file_server` (docs/notes/restructuring.md §12 #4),
		## not yet migrated.
		block = TrappyConfig.optional_block(scopeconfig, "config", "file_server")
		if block is None:
			ExpSync.active = False
			return

		ExpSync.active = True
		ExpSync.server = block["server"]
		ExpSync.share = block["share"]
		ExpSync.username = block["username"]
		ExpSync.password = block["password"]
		ExpSync.destination_fmt = block["destination"]



	def __init__(self, expname, sync_max_threads=1, destination_dir=None):
		"""
		sync_max_threads: maximum number of processes/threads for synching files.
		destination_dir: if not set, a directory is created using the destination
		string in the configuration.
		"""
		self.sync_max_threads = sync_max_threads
		
		## Deduce a mount point for the remote share
		if platform.system() == "Linux":
			log.debug("Plateform is Linux.")
			self.mount_addr = f"/mnt/{ExpSync.share}/"
			# Todo fill for linux.
		elif platform.system() == "Darwin":
			log.debug("Plateform is Darwin (MacOS).")
			self.mount_addr = f"/Volumes/{ExpSync.share}/"
		else:
			log.error("Operating system not implemented.")

		#if not os.path.exists(self.mount_addr):
		self.destination_dir = None
		if ExpSync.active:
			self.mount(ExpSync.server, ExpSync.share, 
					   ExpSync.username, ExpSync.password)

			if not os.path.exists(".sync"):
				self.set_sync_logfile()
					
			## AI Generated -- effify() used to be defined inline right
			## here; centralized onto TrappyConfig.template() (Claude,
			## Anthropic) so any config field wanting this same
			## "{date}"-style templating can reuse it instead of a second
			## private copy. See docs/notes/scripts_measurements_plotting.md §G.10.

			## AI Generated -- destination_dir was computed fresh from
			## today's date/time on every single open (Experiment.__init__
			## looks for self.logs["destination_dir"] to reuse, but nothing
			## ever wrote it back here), so a reconnect on a different day
			## silently negotiated a brand new remote directory instead of
			## reusing the one this experiment already has. Fixed: persist
			## it, and log which of the two actually happened -- see
			## docs/notes/experiment_architecture_and_actions.md §C.
			reconnected = bool(destination_dir)
			if not destination_dir:
				templated = TrappyConfig.current.template(ExpSync.destination_fmt)
				self.mkexpdir(templated, expname)
				self.destination_dir = os.path.join(self.mount_addr, templated, expname)
			else:
				self.destination_dir = destination_dir

			if not os.path.exists(self.destination_dir):
				raise FileNotFoundError("exp.destination_dir not found. Check experiment.yaml file.")

			self.logs["destination_dir"] = self.destination_dir
			self.log("sync_reconnected" if reconnected else "sync_destination_negotiated",
					 attribs={"destination_dir": self.destination_dir})

		## Background executor
		self.__executor = ThreadPoolExecutor(max_workers=sync_max_threads)
		self.__futures = []


	def __get__state__(self):
		return {"active" : ExpSync.active,
				"destination_dir": self.destination_dir,
				"sync_max_threads" : self.sync_max_threads}

	def __exit__(self):
		log.warning("Waiting for transfers...")
		self.__executor.shutdown(wait=True)
		log.warning("[OK] Transfers complete...")

	
	def mkexpdir(self, scopeid, experiment):
		"""
		scopeid: Scopeid.
		experiment: experiment name.
		"""
		try:
			os.makedirs(os.path.join(self.mount_addr, scopeid, experiment), mode=0o777, exist_ok=True)
		except:
			os.system(f"sudo mkdir -p {os.path.join(self.mount_addr, scopeid, experiment)}")
		log.info("Created / confirmed remote Experiment directory.")

	def set_sync_logfile(self):
		"""
		Mark the experiment for synchronisation and use a dot
		file called .sync for logging. This is used to maintain the filetree.
		"""
		syncid = uid()
		log.critical(f"Set experiment syncronisation with syncid: {syncid}")
		with open(".sync", "w") as file:
			file.write(f"syncid:{syncid}, {datetime.datetime.now()}\n")

	def mount(self, server, share, username, password):
		"""
		Mount an SMB share. See core.sync.mount -- not experiment-specific,
		so the actual mounting logic lives there.
		"""
		mount_point = sync.mount(server, share, username, password)
		print(f"Mounted //{server}/{share} at {mount_point}.")
		self.server = f"{mount_point}/"

	def sync_dir(self, remove_source=False):
		"""
		Note: Blocking function

		Synchronise the whole experiment directory to the source.
		"""
		files = [f for f in os.listdir(os.getcwd())]
		files = [file for file in files if not file.startswith(".")]
		if remove_source:
			files = [file for file in files if file not in ["expstate.pickle", \
													   		"experiment.yaml", \
													   		"sessions.yaml"]]

		# Create a ThreadPoolExecutor for parallel execution
		with ThreadPoolExecutor(max_workers=self.sync_max_threads) as __executor:
			if not remove_source:
				results = __executor.map(self.sync_file, files)
			else:
				from functools import partial
				sync_ = partial(self.sync_file, remove_source=remove_source)
				results = __executor.map(sync_, files)

		# Collecting the results (just for demonstration purposes)
		for result in results:
			if result is not None:
				log.debug(result)


	def sync_file_bg(self, file, remove_source=False, delay_sec=0):
		"""
		Same as `sync_file` function, but is non-blocking manner.
		This uses a threadpool. The number of workers can be set,
		while creating the experiment.
		"""
		self.__executor.submit(self.sync_file, file, remove_source=remove_source, \
							 delay_sec=delay_sec)

	def sync_file(self, file, remove_source=False, delay_sec=0):
		"""
		Note: Blocking function

		Run rsync for a specific file or directory.
		file: filename (relative to exp_dir)
		remove_source: transfers the sourcefile vs copy
		delay_sec: delay the transfer by a number of seconds. This is useful in
		case, the transfers need to be staggered because of bandwidth limitations.
		"""

		# To account for file write delays for example.
		if delay_sec:
			time.sleep(delay_sec)

		## -W --no-compress --inplace: large binary experiment files (video,
		## images) don't benefit from rsync's delta-transfer algorithm or
		## compression -- the whole-file copy is cheaper than the comparison
		## overhead. ionice throttles I/O priority so this doesn't compete
		## with a live experiment still writing to the same disk.
		result = sync.sync(
			os.path.join(os.getcwd(), file),
			os.path.join(self.destination_dir, file),
			flags=["-a", "-W", "--no-compress", "--inplace"],
			remove_source=remove_source,
			prefix=["sudo", "ionice", "-c2", "-n4"],
		)
		if result.returncode != 0:
			log.error(f"Error occurred with {file}: {result.stderr.strip()}")
			return None

		log.info(f"Rsync completed for {file}")
		print(f"Rsync completed for {file}")
		if remove_source:
			with open(".sync", "a") as f:
				f.write(f"{file}, {datetime.datetime.now()}\n")
		return result.stdout



# Example usage
if __name__ == '__main__':
	print("This program will not execute. It is an example.")
	source_directory = '/path/to/source/directory'
	destination_directory = '/path/to/destination/directory'
	
	# Set the maximum number of parallel workers
	#max_parallel_workers = 4
	
	# Start the rsync process
	#rsync_directory(source_directory, destination_directory, max_parallel_workers)




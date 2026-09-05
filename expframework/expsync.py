from rich import print
import os
import logging as log
import asyncio
import subprocess
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
import datetime


from core.uid import uid
from core.permaconfig.sharing import Share
from core.permaconfig.config import TrappyConfig
from core.bookkeeping.user import User

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
					
			date = Share.get_date_str()
			time = Share.get_time_str()
			user = User.name()
			scopeid = Share.scopeid

			def effify(non_f_str: str, locals_):
				return eval(f'f"""{non_f_str}"""', locals_)

			if not destination_dir:
				self.mkexpdir(effify(ExpSync.destination_fmt, locals()), expname)
				self.destination_dir = os.path.join(self.mount_addr, effify(ExpSync.destination_fmt, locals()), expname)
			else:
				self.destination_dir = destination_dir

			if not os.path.exists(self.destination_dir):
				raise FileNotFoundError("exp.destination_dir not found. Check experiment.yaml file.")

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
		Mount an SMB share at a specified mount point.
		
		:param server: SMB server address (e.g., 192.168.1.10)
		:param share: SMB share name (e.g., shared_folder)
		:param mount_point: Local directory to mount the share
		:param username: SMB username
		:param password: SMB password
		"""
		import platform

		if platform.system() == "Linux":
			log.debug("Plateform is Linux.")
			mount_point = "/mnt"
			mount_cmd = ["sudo", "mount", "-t", "cifs", f"//{server}/{share}", \
						f"{mount_point}/{share}", "-m", "-o", \
						f"username={username},password={password},rw,file_mode=0777,dir_mode=0777,uid=1000,gid=1000"]
			try:
				subprocess.run(mount_cmd, check=True)
				print(f"Mounted //{server}/{share} at {mount_point}/{share}.")
				time.sleep(5)
			except Exception as e:
				print(e)
				if "error(16)" in str(e):
					log.info("file_server is already mounted!")
			print(f"{mount_point} dir for reference: ", os.listdir(mount_point))
			self.server = f"{mount_point}/{share}/"
		elif platform.system() == "Darwin":
			log.debug("Plateform is Darwin (MacOS).")
			try:
				mount_point = "/Volumes"
				mount_cmd = ["open", f"smb://{username}:{password}@{server}/{share}"]
				subprocess.run(mount_cmd, check=True)
				print(f"Mounted //{server}/{share} at {mount_point}/{share}.")
				time.sleep(5)
				print("/Volumes dir for reference: ", os.listdir("/Volumes"))
				self.server = f"{mount_point}/{share}/"
			except subprocess.CalledProcessError as e:
				print(f"Error mounting SMB share: {e}")
		else:
			log.error("Unsupported plateform (os).")
			return

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

		source_removal = []
		if remove_source:
			source_removal.append('--remove-source-files')
		try:
			# Running rsync command
			#ionice -c1 -n0 rsync -aW --inplace --no-compress /source/ /mnt/nas/

			command = [
				'sudo', 'ionice', '-c2', '-n4', 'rsync', '-aW', '--no-compress', '--inplace', *source_removal,
				os.path.join(os.getcwd(), file),
				os.path.join(self.destination_dir, file)
			]
			result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			log.info(f"Rsync completed for {file}")
			print(f"Rsync completed for {file}")
			if remove_source:
				with open(".sync", "a") as f:
					f.write(f"{file}, {datetime.datetime.now()}\n")
			return result.stdout.decode()
		except subprocess.CalledProcessError as e:
			log.error(f"Error occurred with {file}: {e.stderr.decode()}")
			return None



# Example usage
if __name__ == '__main__':
	print("This program will not execute. It is an example.")
	source_directory = '/path/to/source/directory'
	destination_directory = '/path/to/destination/directory'
	
	# Set the maximum number of parallel workers
	#max_parallel_workers = 4
	
	# Start the rsync process
	#rsync_directory(source_directory, destination_directory, max_parallel_workers)




import datetime

class Session:
	def create_session(scope_name, datastore, sensors\
					   experiment_mode=False, experiment_id=None,
					   create_session_folder=True):
		"""
		Create a session in the `data` folder.
		A session generates a directory and some basic metadata structure.
		"""
		# In experiment mode, no session folder will be created by default.
		if experiment_mode:
			create_session_folder = False

		# 1. ´data´ folder exists
		if not os.path.exists("./data"):
			os.mkdir("./data")
			print("Created `data` folder —> primary node.")

		# 2. Create date folder
		if not experiment_mode:
			now = datetime.datetime.now()
			date_folder = f"{scope_name}__{now.day}__{now.month}__{now.year}"
			extended_path = os.path.join("./data", date_folder)
			if not os.path.exists(os.path.join("./data", date_folder)):
				os.mkdir(extended_path)
				print(f"Created today's session folder: {os.abspath(extended_path)}")
				
		
		else: # Experiment Mode (One Folder for one experiment)
			if not experiment_id:
				print("Error! No Experiment name was given!")
				exit(1)
			else:
				now = datetime.datetime.now()
				date_folder = f"{scope_name}__{experiment_id}"
			extended_path = os.path.join("./data", date_folder)
			if not os.path.exists(extended_path):
				os.mkdir(extended_path)
				print(f"Created experiment folder: {os.abspath(extended_path)}")
			extended_path = os.path.join(extended_path, f"{now.day}__{now.month}__{now.year}")
			if not os.path.exists(extended_path):
				os.mkdir(extended_path)
				print(f"Created date specific experiment folder: {os.abspath(extended_path)}")


		# 3. Create sessions metadata
		session_md = MetaData("session")
		session_md.add_que("What is the session name?", label="name", default="unnamed")

		# This will persist until the Session is terminated
		session_defaults_by_user = {     
									 "scope_name"            : scope_name
									 "cell_strain"           : "CC125",
									 "cell_culture_id"       : None,
									 "session_duration_s"    : None,
									 "path"                  : extended_path,
								 	 "rel_path"              : extended_path,
		}

		self.metadata = session_defaults_by_user
		session_md.add_que("What is the cell strain being used?", label="cell_strain")
		session_md.add_que("What is the cell culture id?", label="cell_culture_id")

		session_md.collect()

		# Environmental input collected by sensor array
		tandh_read = sensors["tandh"].get()
		environment_metadata  = {
									"temp_C"                : tandh_read["temp"],
								 	"humidity"              : tandh_read["humidity"]
		}
		session_md.add_node(environment_metadata)


		acq_folder = extended_path 
		if create_session_folder:
			session_folder_name = session_md.file_descriptor(include=["scope_name"])
			os.mkdir(session_folder_name)
			print(f"Session generated: {session_folder_name}")
			acq_folder = session_folder_name
			
		return {"metadata": session_md, "acq_folder": acq_folder}
		#datastore.new(session_md.file_descriptor())


	def acq_metadata(acq_modes):
		"""
		Creates acquisition metadata. This function must be ideally called by the 
		"""

		# Default Aquisitions
		acq_defaults = {
							"mode"           : "video",
							"tsec"           : 30,
							"illumination_V" : (2,2,2),
							"preview"        : True,

							# Can be skipped
							"iterations"     : 1,
							"delay_s"        : 0,

							# To be calculated after acquisition
							"acq_time_s"     : None,
							"capture_lag"    : None
						}

		acq_md = MetaData("acq"):
		acq_md.add_que(f'Acquisition mode {acq_modes}: ', label="acq_mode")
		for key in acq_defaults.keys().remove(["acq_time_s", "capture_lag"]):
			acq_md.add_que(f"{key} ?", label=key)
		acq_md.collect()

		if acq_md.collected:
			return acq_md.metadata
		else:
			return (None, acq_defaults)
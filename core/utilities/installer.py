
### Minimal imports. Remeber nothing exists yet. Only libraries in the standard
### Distribution
import os
import sys

class Installer:
	pylibs = ["rich", "pyyaml", "colorama", "nanoid", "art",
			  "plotext", "asciichartpy", "prompt_toolkit", 
			  "GitPython", "schedule", "websockets", 
			  "pandas", "textual", "pyserial", "pypandoc",
			  "confuse", "matplotlib", "scikit-image", "html2rml",
			  "rpyc", 
			  "numpy<2.0.0"]
	
	binlibs = []
	gitclones = ["https://github.com/Trappy-Scopes/network.git", 
				"https://github.com/Trappy-Scopes/secrets.git"]
	

	def do_all():

		platform = sys.platform.startswith('linux')*"linux" + \
		           sys.platform.startswith('darwin')*"darwin"
		if not platform:
			print("We don't do Windows! Sorry!")
			exit()

		print(f"Plateform is: {platform}.")
		if platform == "darwin":
			print("Please ensure that `brew` package manager is installed.")


		print(f"You are ready to trap cells, you just need the following: \
			  \npython libraries: {Installer.pylibs} \
			  \nother libraries: {Installer.binlibs}")
		x = input("Let's go, we will need sudo previledges [press Enter]:")


		## python
		Installer.install_py_libs(Installer.pylibs)
		#Installer.install_bin_libs(Installer.binlibs)
		#Installer.gitclone(Installer.gitclones)
		Installer.check_submodules()

		
		## Also check if the submodules are properly installed here

		### -----

		print("\n\nIf everyhting went well, we are ready to go!\n\n")

		

	def install_py_libs(required_libs):

		for i, lib in enumerate(required_libs):
			try: 
				__import__(lib)
				print(f"{i}. {lib} : already exists!")
			except ImportError:
				#pip.main(['install', lib, "--break-system-packages"])
				os.system(f"sudo pip install {lib} --break-system-packages")
				print(f"{i}. {lib} : was installed!")

	def install_bin_libs(required_libs):
		pass

	def gitclone(dir_="../"):

		from git import Repo

		dir_ = os.path.abspath(dir_)
		required_libs = list(required_libs)
		
		for lib in required_libs:
			print(f"Git clone: Checking :  {lib}")
			lib_name = lib.split("/")[-1].rstrip(".git")  
			installer = lambda:	os.system(f"git clone {lib} -C {dir_}")
			if not os.path.isdir(os.path.join(dir_, lib_name)):
				installer()
			else:
				try:
					repo = Repo(os.path.join(dir_, lib_name))
				except:
					installer()

			

	def check_submodules():
		pass
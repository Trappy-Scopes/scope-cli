

def sys_perma_state():
	"""
	Device state which is not subject to change and can be reliably collected anytime.
	"""
	from uuid import getnode as get_mac
	from socket import gethostname, gethostbyname
	import platform
	mac=get_mac()
	mac_str=':'.join(("%012X" % mac) [i:i+2] for i in range(0,12,2))

	# If the IP address thing doesn't work.

	# Non-mutable configs
	ds =  {
		   # Hardware/Raspberry Pi Settings
		   "mac_address" : mac_str,
		   #"ip_address"  : gethostbyname(gethostname()),
		   "hostname"    : gethostname(),
		   "os"          : [platform.system(), platform.release()]
		  }
	return ds
import ast

def resolve_type(string):
	try:
		value = ast.literal_eval(string)
		return value
	except:
		return str(string)
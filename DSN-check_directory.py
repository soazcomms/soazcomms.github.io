import os

def ls(path='.'):
    """Lists files and directories in the given path."""
    for entry in os.listdir(path):
        print(entry)

def check_directory(directory):
    try:
        files = os.listdir(directory)
        print(f"Files in '{directory}': {files}")
    except Exception as e:
        print(f"Error checking directory: {e}")

# directory to check
print("DIR: ",os.getcwd())
os.chdir("./DSNdata/NEW")
# List files in the current directory
ls()

# List files in a specific directory
#ls("/home/runner/work/soazcomms/DSNdata/NEW")

#directory_to_check = '/home/runner/work/soazcomms'
#/home/runner/work/soazcomms.github.io/soazcomms.github.io

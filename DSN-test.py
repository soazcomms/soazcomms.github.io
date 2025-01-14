import os

def check_directory(directory):
    try:
        files = os.listdir(directory)
        print(f"Files in '{directory}': {files}")
    except Exception as e:
        print(f"Error checking directory: {e}")

# Example directory to check
directory_to_check = 'DSNdata/NEW'  # Replace with your directory path
check_directory(directory_to_check)
print("Hello Universe")

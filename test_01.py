import os
import shutil

# specify the path of the folder containing the files
folder_path = "/Users/yommi/Downloads"

# create a dictionary to store the extensions and their respective folders
extension_folders = {}

# loop through the files in the folder
for file_name in os.listdir(folder_path):
    print(f"file_name:: {file_name}")
    # get the extension of the file
    extension = os.path.splitext(file_name)[1]
    print(f"extension:: {extension}")
    print(type(extension))
    if extension is None or extension == "":
        continue

    # check if the extension has been added to the dictionary yet
    if extension not in extension_folders:
        # if not, create a new folder for the extension
        extension_folder = os.path.join(folder_path, extension[1:])
        os.makedirs(extension_folder, exist_ok=True)
        extension_folders[extension] = extension_folder

    # move the file to its respective folder
    src_path = os.path.join(folder_path, file_name)
    dst_path = os.path.join(extension_folders[extension], file_name)
    shutil.move(src_path, dst_path)

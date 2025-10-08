import json
import subprocess
import tempfile
import os

miniver = os.getenv("MINIVER")
splenv = os.getenv("SPLENV_REF")

folders = ["manifests/", "env/", "tables/"]
BUCKET_NAME = "eups-prod"
GCS_PREFIX = f"gs://{BUCKET_NAME}"
INDEX_FILE = "index.json"


root_folders = [
    "stack/redhat/el7/conda-system",
    "stack/redhat/el8-arm/conda-system",
    "stack/osx/14-arm/conda-system",
]


# If we have the MINIVER and SPLENV_REF defined, then we can return
# a string to filter by
def filter_folders() -> str:
    if miniver and splenv:
        return f"miniconda3-{miniver}-{splenv}"
    return ""


def get_gcs_object_uris(target: str) -> list[str]:
    indexdata = subprocess.run(
        ["gcloud", "storage", "ls", target], capture_output=True, check=True, text=True
    )
    return indexdata.stdout.split()


def copy_files(file: str, target: str):
    copy = subprocess.run(
        ["gcloud", "storage", "cp", file, target + INDEX_FILE],
        capture_output=True,
        check=True,
        text=True,
    )
    if copy.returncode == 0:
        print(f"updated {INDEX_FILE}")


def update_helper(loc: str):
    target = f"{GCS_PREFIX}/{loc}"
    print(target)
    # Using the gcloud cli tool was the most consistant way to get file names.
    # SDK would give a mix of folders and files
    indexdata = []
    try:
        indexdata = get_gcs_object_uris(target)
    except subprocess.CalledProcessError:
        print(f"{target} does not exist, skipping")
        return
    # makes a list of all the filenames in the target. It filters out folders
    # because folders will be empty strings
    # index = [file for i in indexdata for file in [i.split("/")[-1]] if file]
    index = [i.split("/")[-1] for i in indexdata if i]
    with tempfile.NamedTemporaryFile("w", delete_on_close=False) as f:
        json.dump(index, f)
        f.close()
        print("Fetched files")
        copy_files(f.name, target)
        os.remove(f.name)


def get_list_of_folders() -> list[str]:
    conda_folder = []
    for folder in root_folders:
        target = f"{GCS_PREFIX}/{folder}"
        indexdata = None
        try:
            indexdata = get_gcs_object_uris(target)
        except subprocess.CalledProcessError:
            print(f"{target} does not exist, skipping")
            continue
        for j in indexdata:
            conda_folder.append(j.removeprefix(f"{GCS_PREFIX}/"))
    return conda_folder


def main():
    platforms = ["stack/src/"]
    # Gets all of the folders
    platforms.extend(get_list_of_folders())

    # If miniver and splenv are set, filter out folders that are not included
    platforms = [p for p in platforms if filter_folders() in p or "src/" in p]
    for p in platforms:
        if "src" in p:
            # Src folder contains extra folders
            srcfolders = folders + ["products/", "tags/"]
            for f in srcfolders:
                prefix = p + f
                update_helper(prefix)
        else:
            update_helper(p)
            for f in folders:
                prefix = p + f
                update_helper(prefix)


if __name__ == "__main__":
    main()

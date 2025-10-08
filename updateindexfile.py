import json
import subprocess
import tempfile
import os

TMPFILE = "/tmp/index.json"

miniver = os.getenv("MINIVER")
splenv = os.getenv("SPLENV_REF")

folders = ["manifests/", "env/", "tables/"]
bucket_name = "eups-prod"

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


def update_helper(loc: str):
    target = f"gs://{bucket_name}/{loc}"
    print(target)
    # Using the gcloud cli tool was the most consistant way to get file names.
    # SDK would give a mix of folders and files
    indexdata = None
    try:
        indexdata = subprocess.run(
            ["gcloud", "storage", "ls", target], capture_output=True, check=True, text=True
        )
    except subprocess.CalledProcessError:
        print(f"{target} does not exist, skipping")
        return
    indexdata = indexdata.stdout.split()
    index = [i.split("/")[-1] for i in indexdata]
    with tempfile.NamedTemporaryFile("w", delete_on_close=False) as tmpfile:
        json.dump(index, tmpfile)
        tmpfile.close()
        print("Fetched files")
        copy = subprocess.run(
            ["gcloud", "storage", "cp", tmpfile.name, target + "index.json"],
            capture_output=True,
            check=True,
            text=True,
        )
        if copy.returncode == 0:
            print("updated index.json")


def get_list_of_folders() -> list[str]:
    conda_folder = []
    for folder in root_folders:
        target = f"gs://{bucket_name}/{folder}"
        indexdata = subprocess.run(
            ["gcloud", "storage", "ls", target], capture_output=True, check=True, text=True
        )
        indexdata = indexdata.stdout.split()
        for j in indexdata:
            conda_folder.append(j.split(f"gs://{bucket_name}/")[1])
    return conda_folder


def check_for_index_file(src: str) -> int:
    src = "https://eups.lsst.cloud/" + src
    print("Checking ", src)
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "200", src], capture_output=True, text=True)
    print(r.stdout)
    if r.stdout != "200":
        raise ValueError
    return int(r.stdout)


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
            check_for_index_file(prefix)
    else:
        update_helper(p)
        print(p)
        for f in folders:
            prefix = p + f
            update_helper(prefix)

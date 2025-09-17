import json
import subprocess
import tempfile

TMPFILE = "/tmp/index.json"
# We should look for a way to get the names automatically. GCP sdk was not able to help with this.
folders = ["manifests/", "env/", "tables/"]
bucket_name = "eups-prod"

root_folders = ["stack/redhat/el7/conda-system","stack/redhat/el8-arm/conda-system","stack/osx/14-arm/conda-system"]

def update_helper(loc: str):
    target = f"gs://{bucket_name}/{loc}"
    print(target)
    # Using the gcloud cli tool was the most consistant way to get file names. SDK would give a mix of folders and files
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

def get_list_of_folders()-> list[str]:
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
    print("Checking ",src)
    r = subprocess.run(["curl", "-s", "-o", '/dev/null', '-w', "200", src], capture_output=True, text=True)
    print(r.stdout)
    if r.stdout != "200":
        raise ValueError
    return int(r.stdout)

platforms = ["stack/src/"]
platforms.extend(get_list_of_folders())

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
        for f in folders:
            prefix = p + f
            update_helper(prefix)
            check_for_index_file(prefix)

import json
import subprocess

TMPFILE = "/tmp/index.json"
# We should look for a way to get the names automatically. GCP sdk was not able to help with this.
platforms = [
    "stack/redhat/el7/conda-system/miniconda3-py38_4.9.2-10.0.0/",
    "stack/redhat/el8-arm/conda-system/miniconda3-py38_4.9.2-10.0.0/",
    "stack/src/",
    "stack/osx/14-arm/conda-system/miniconda3-py38_4.9.2-10.0.0/",
]
folders = ["manifests/", "env/", "tables/"]
bucket_name = "eups-prod"


def update_helper(loc):
    print(loc)
    target = f"gs://{bucket_name}/{loc}"
    # Using the gcloud cli tool was the most consistant way to get file names. SDK would give a mix of folders and files
    indexdata = subprocess.run(
        ["gcloud", "storage", "ls", target], capture_output=True, check=True, text=True
    )
    indexdata = indexdata.stdout.rsplit()
    index = []
    for i in indexdata:
        index.append(i.split("/")[-1])
    indexjson = json.dumps(index)
    with open(TMPFILE, "w") as f:
        f.write(indexjson)
    print("Fetched files")
    copy = subprocess.run(
        ["gcloud", "storage", "cp", TMPFILE, target], capture_output=True, check=True, text=True
    )
    if copy.returncode == 0:
        print("updated index.json")


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

# This is a quick helper script to generate a unique hex key for the jupyterhub before deploying the helmchart
# It is executed on the control node after the entire cluster cloudformationn is deployed

import yaml
import subprocess


hex = subprocess.check_output(["openssl", "rand", "-hex", "32"])
print(hex)

with open("helm_config.yaml") as f:
    helm_config = yaml.load(f)

helm_config["proxy"]["secretToken"] = hex.decode('ascii').strip()

with open("helm_config.yaml", "w") as f:
    yaml.dump(helm_config, f, default_flow_style=False)

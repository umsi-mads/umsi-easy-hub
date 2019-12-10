# This is a quick helper script to set the single user memory limit/guarantee in the helm_config.yaml
# It is executed on the control node after the entire cluster cloudformationn is deployed

import yaml
import subprocess


# Get user pod memory from config.yaml

with open("config.yaml") as f:
    config = yaml.load(f)

memory = config["common"]["UserPodMemory"]

# Now enter the value in the helm_config.yaml

with open("helm_config.yaml") as f:
    helm_config = yaml.load(f)

helm_config["singleuser"]["memory"]["limit"] = "{}G".format(memory)
helm_config["singleuser"]["memory"]["guarantee"] = "{}G".format(memory)

with open("helm_config.yaml", "w") as f:
    yaml.dump(helm_config, f, default_flow_style=False)

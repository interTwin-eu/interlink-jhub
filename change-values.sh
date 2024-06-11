#!/bin/bash

# create a copy of the file jupyter_template.py
cp jupyter_template.py jupyterhubcustomconfig.py
cp values_template.yaml values.yaml

source .env

HOSTNAME="jhub.131.154.98.62.myip.cloud.infn.it"

# values inside jupyter_template.py
IAM_SERVER="https://iam.cloud.infn.it"
CALLBACK_URL="https://$HOSTNAME:443/hub/oauth_callback"
JHUB_HOST="$HOSTNAME"
JHUB_PORT="443"
JHUB_API_URL="https://$HOSTNAME/hub/api"
VK_NODENAME='my-iam-node'
GPU_CAP="2"

sed -i "s|__CALLBACK_URL__|\"$CALLBACK_URL\"|g" jupyterhubcustomconfig.py
sed -i "s|__IAM_SERVER__|\"$IAM_SERVER\"|g" jupyterhubcustomconfig.py
sed -i "s|__CLIENT_ID__|\"$CLIENT_ID\"|g" jupyterhubcustomconfig.py
sed -i "s|__CLIENT_SECRET__|\"$CLIENT_SECRET\"|g" jupyterhubcustomconfig.py
sed -i "s|__COOKIE_SECRET__|\"$COOKIE_SECRET\"|g" jupyterhubcustomconfig.py
sed -i "s|__JHUB_HOST__|\"$JHUB_HOST\"|g" jupyterhubcustomconfig.py
sed -i "s|__JHUB_IP__|\"$HOSTNAME\"|g" jupyterhubcustomconfig.py
sed -i "s|__JHUB_PORT__|\"$JHUB_PORT\"|g" jupyterhubcustomconfig.py
sed -i "s|__JHUB_API_URL__|\"$JHUB_API_URL\"|g" jupyterhubcustomconfig.py
sed -i "s|__VK_NODENAME__|\"$VK_NODENAME\"|g" jupyterhubcustomconfig.py
sed -i "s|__GPU_CAP__|\"$GPU_CAP\"|g" jupyterhubcustomconfig.py

# values inside values.yaml
JHUB_URL="https://$HOSTNAME:443"
NAMESPACE="helm-jhub-namespace"
RELEASE="helm-jhub-release"

sed -i "s|__JHUB_URL__|\"$JHUB_URL\"|g" values.yaml
sed -i "s|__JHUB_HOSTNAME__|\"$JHUB_HOST\"|g" values.yaml
sed -i "s|__NAMESPACE__|$NAMESPACE|g" values.yaml
sed -i "s|__RELEASE__|\"$RELEASE\"|g" values.yaml
sed -i "s|__CALLBACK_URL__|\"$CALLBACK_URL\"|g" values.yaml
sed -i "s|__IAM_SERVER__|\"$IAM_SERVER\"|g" values.yaml
sed -i "s|__COOKIE_SECRET__|$COOKIE_SECRET|g" values.yaml

# check if jhub folder exists, if not create it
if [ ! -d "jhub" ]; then
  mkdir jhub
fi

mv jupyterhubcustomconfig.py jhub/jupyterhubcustomconfig.py

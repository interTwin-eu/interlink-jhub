#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import socket
import json
from oauthenticator.oauth2 import OAuthenticator
from oauthenticator.generic import GenericOAuthenticator
from tornado import gen

# Fix for latest jhub server version
from tornado.httpclient import AsyncHTTPClient
import kubespawner
import subprocess
import warnings

import pprint
import jwt

import os
from subprocess import check_call
import asyncio

import kubernetes_asyncio as k8s
import nest_asyncio

callback_url = __CALLBACK_URL__
iam_server = __IAM_SERVER__
client_id = __CLIENT_ID__
client_secret = __CLIENT_SECRET__
cookie_secret_str = __COOKIE_SECRET__
jhub_host = __JHUB_HOST__
jhub_ip = __JHUB_IP__
jhub_port = __JHUB_PORT__
jhub_api_url = __JHUB_API_URL__

cookie_secret_bytes = cookie_secret_str.encode('utf-8')
os.environ["OAUTH_CALLBACK"] = callback_url
cache_file = './iam_secret'

cache_results = {
    "client_id": client_id,
    "client_secret": client_secret
}

with open(cache_file, "w") as w:
    json.dump(cache_results, w)

client_id = cache_results["client_id"]
client_secret = cache_results["client_secret"]

class EnvAuthenticator(GenericOAuthenticator):

    @gen.coroutine
    def pre_spawn_start(self, user, spawner):

        auth_state = yield user.get_auth_state()
        pprint.pprint(auth_state)
        if not auth_state:
            # user has no auth state
            return
        # define some environment variables from auth_state
        self.log.info(auth_state)
        spawner.environment['IAM_SERVER'] = iam_server
        spawner.environment['IAM_CLIENT_ID'] = client_id
        spawner.environment['IAM_CLIENT_SECRET'] = client_secret
        spawner.environment['ACCESS_TOKEN'] = auth_state['access_token']
        spawner.environment['REFRESH_TOKEN'] = auth_state['refresh_token']
        spawner.environment['USERNAME'] = auth_state['oauth_user']['preferred_username']
        spawner.environment['JUPYTERHUB_ACTIVITY_INTERVAL'] = "15"
        spawner.environment['SSH_NAMESPACE'] = os.environ.get("SSH_NAMESPACE") 

        amIAllowed = False
        
        groups = jwt.decode(auth_state["access_token"], options={"verify_signature": False, "verify_aud": False})["wlcg.groups"]
        groups = [s[1:] for s in groups]
        
        if os.environ.get("OAUTH_GROUPS"):
            spawner.environment['GROUPS'] = " ".join(groups)
            allowed_groups = os.environ["OAUTH_GROUPS"].split(" ")
            amIAllowed = any(gr in groups for gr in allowed_groups)
        else:
            amIAllowed = True

        if not amIAllowed:
                self.log.error(
                    "OAuth user contains not in group the allowed groups %s" % allowed_groups
                )
                raise Exception("OAuth user not in the allowed groups %s" % allowed_groups)

    async def authenticate(self, handler, data=None):

        code = handler.get_argument("code")
        #http_client = self.http_client()
        
        # Fix for latest jhub server version
        http_client = AsyncHTTPClient()

        params = dict(
            redirect_uri=self.get_callback_url(handler),
            code=code,
            grant_type='authorization_code',
        )
        params.update(self.extra_params)
        headers = self._get_headers()

        #token_resp_json = await self._get_token(http_client, headers, params)

        # Fix for latest jhub server version
        token_resp_json = await self._get_token(headers, params)

        #user_data_resp_json = await self._get_user_data(http_client, token_resp_json)
        # Fix for latest jhub server version
        user_data_resp_json = await self._get_user_data(token_resp_json)

        if callable(self.username_key):
            name = self.username_key(user_data_resp_json)
        else:
            name = user_data_resp_json.get(self.username_key)
            if not name:
                self.log.error(
                    "OAuth user contains no key %s: %s", self.username_key, user_data_resp_json
                )
                return

        auth_state = self._create_auth_state(token_resp_json, user_data_resp_json)
        groups = jwt.decode(auth_state["access_token"], options={"verify_signature": False, "verify_aud": False})["wlcg.groups"]
                        
        is_admin = False
        if os.environ.get("ADMIN_OAUTH_GROUPS") in groups:
            self.log.info("%s : %s is in %s" , (name, os.environ.get("ADMIN_OAUTH_GROUPS"), groups))
            is_admin = True
        else:
            self.log.info(" %s is not in admin group ", name)

        return {
            'name': name,
            'admin': is_admin,
            'auth_state': auth_state #self._create_auth_state(token_resp_json, user_data_resp_json)
        }

c.JupyterHub.tornado_settings = {'max_body_size': 1048576000, 'max_buffer_size': 1048576000}
c.JupyterHub.log_level = 30
c.JupyterHub.hub_connect_ip = jhub_ip
c.JupyterHub.api_url = jhub_api_url
c.JupyterHub.cookie_secret = cookie_secret_bytes


c.JupyterHub.authenticator_class = EnvAuthenticator
c.Spawner.default_url = '/lab'
c.GenericOAuthenticator.oauth_callback_url = callback_url
c.GenericOAuthenticator.client_id = client_id
c.GenericOAuthenticator.client_secret = client_secret
c.GenericOAuthenticator.authorize_url = iam_server.strip('/') + '/authorize'
c.GenericOAuthenticator.token_url = iam_server.strip('/') + '/token'
c.GenericOAuthenticator.userdata_url = iam_server.strip('/') + '/userinfo'
c.GenericOAuthenticator.scope = ['openid', 'profile', 'email', 'address', 'offline_access', 'wlcg', 'wlcg.groups']
c.GenericOAuthenticator.username_key = "preferred_username"
c.GenericOAuthenticator.enable_auth_state = True

class CustomSpawner(kubespawner.KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.map_node_gpu = {}

    def get_args(self):
        # Get the default arguments
        args = super().get_args()
        if self.image == "biancoj/jlab-ai":
            args.extend([
                "/opt/conda/bin/python3",
                "/usr/local/bin/jupyterhub-singleuser"
            ])
        elif self.image == "ghcr.io/dodas-ts/htc-dask-wn:v1.0.6-ml-infn-ssh-v5":
            args.extend([
                "/opt/ssh/jupyterhub-singleuser"
            ])

        # Add custom arguments
        args.extend([
            "--ip=0.0.0.0",
            "--port="+str(self.port),
            "--SingleUserNotebookApp.default_url=/lab",
            "--notebook-dir=/home/jovyan",
            "--debug",
            "--allow-root"
        ])

        return args
    
    async def _get_nodes(self):

        k8s.config.load_incluster_config()

        async with k8s.client.api_client.ApiClient() as api_client:
            core = k8s.client.CoreV1Api(api_client)
            nodes = await core.list_node()

        return nodes.items
    
    async def _get_pods(self):
        k8s.config.load_incluster_config()

        async with k8s.client.api_client.ApiClient() as api_client:
            core = k8s.client.CoreV1Api(api_client)
            pods = await core.list_pod_for_all_namespaces()
        
        return pods.items
    
    def _options_form_default(self):
        options_to_return = """
        <label for="stack">Select your desired image:</label>
        <br>
        <input type="radio" id="option1" name="img" value="ghcr.io/dodas-ts/htc-dask-wn:v1.0.6-ml-infn-ssh-v5">
        <label for="option1">ghcr.io/dodas-ts/htc-dask-wn:v1.0.6-ml-infn-ssh-v5</label><br>
        <a href="https://github.com/DODAS-TS/dodas-docker-images" target="_blank">Source docker image from DODAS</a>
        <br>
        <input type="radio" id="option2" name="img" value="biancoj/jlab-ai">
        <label for="option2">biancoj/jlab-ai</label><br>
        <a href="https://github.com/landerlini/ai-infn-platform/tree/main/docker" target="_blank">Source docker image (from ai-infn platform)</a>
        <br>
        <br>
        <label for="cpu">Select your desired number of cores:</label>
        <select name="cpu" size="1">
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="4">4</option>
        <option value="8">8</option>
        </select>
        <br>
        <br>
        <label for="mem">Select your desired memory size:</label>
        <select name="mem" size="1">
        <option value="2G">2GB</option>
        <option value="4G">4GB</option>
        <option value="8G">8GB</option>
        <option value="16G">16GB</option>
        <option value="32G">32GB</option>
        <option value="64G">64GB</option>
        </select>
        <br>
        <br>
        """

        nest_asyncio.apply()
        nodes = asyncio.run(self._get_nodes())
        vk_nodes = [node for node in nodes if node.metadata.labels.get('type') == 'virtual-kubelet']

        nodes_labels = []
        
        available_gpus = 0
        for node in vk_nodes:
            # append the node label to the list nodes_labels
            nodes_labels.append(node.metadata.labels.get('accelerator', ''))
            available_gpus += int(node.status.capacity.get('nvidia.com/gpu', 0))

            if node.metadata.labels.get('accelerator', '') == "T4":
                self.map_node_gpu[node.metadata.labels.get('accelerator', '')] = { "hostname": node.metadata.name, "gpus": int(node.status.capacity.get('nvidia.com/gpu', 0))}
            elif node.metadata.labels.get('accelerator', '') == "none":
                self.map_node_gpu[node.metadata.labels.get('accelerator', '')] = { "hostname": node.metadata.name, "gpus": 0}
        
        options_to_return += '<p><b>GPU Offloading Options</b></p>'
        already_allocated_gpus = 0

        pods = asyncio.run(self._get_pods())
        running_pods = [pod for pod in pods if pod.status.phase == "Running"]
        #print("Running pods: ", len(running_pods))
        for pod in running_pods:
            try:
                for container in pod.spec.containers:
                    if container.resources and 'nvidia.com/gpu' in container.resources.limits:
                            pprint.pprint(pod.metadata.name)
                            already_allocated_gpus += int(container.resources.limits['nvidia.com/gpu'])
            except Exception as e:
                pass

        if available_gpus > 0:
            options_to_return += f"<p>Total GPUs available: <b style='color: darkgreen;'>{available_gpus}</b></p>"

        if already_allocated_gpus > 0:
            options_to_return += f"<p>Used GPUs: <b style='color: darkred;'>{already_allocated_gpus}</b></p>"
        else:
            options_to_return += f"<p>Used GPUs: <b>0</b></p>"

        unused_gpus = available_gpus - already_allocated_gpus
        if unused_gpus > 0:
            options_to_return += f"<p>Unused GPUs: <b>{unused_gpus}</b></p>"
        else:
            options_to_return += f"<p>Unused GPUs: <b>0</b></p>"

        options_to_return += '<label for="offload">Enable Offloading to:</label>'
        options_to_return += '<select name="offload" size="1">'
        for label in nodes_labels:
            options_to_return += f'<option value="{label}">{label}</option>'
            
        if already_allocated_gpus > 0:
            options_to_return += '<p><b>You cannot use a GPU because someone else is using it</b></p>'

        options_to_return += '</select><br>'

        return options_to_return

    def options_from_form(self, formdata):
        options = {}
        options['img'] = formdata['img']
        container_image = ''.join(formdata['img'])
        self.image = container_image

        options['cpu'] = formdata['cpu']
        cpu = ''.join(formdata['cpu'])

        self.cpu_guarantee = float(cpu)
        self.cpu_limit = float(cpu)

        options['mem'] = formdata['mem']
        memory = ''.join(formdata['mem'])
        self.mem_guarantee = memory
        self.mem_limit = memory

        options['offload'] =  ''.join(formdata['offload'])

        sock = socket.socket()
        sock.bind(('', 0))

        self.port = sock.getsockname()[1]


        if options['offload'] == 'T4': # WIP: this should be modify based on the annotations, for example instead of 'vkgpu' should be 'T4'
            self.tolerations = [
                {
                    "key": "accelerator",
                    "operator": "Equal",
                    "value": "T4",
                    "effect": "NoSchedule"
                },
                {
                    "key": "virtual-node.interlink/no-schedule",
                    "operator": "Exists",
                    "effect": "NoSchedule"
                }
            ]
            self.extra_resource_guarantees = {"nvidia.com/gpu": "1"}
            self.extra_resource_limits = {"nvidia.com/gpu": "1"}
        elif options['offload'] == 'NO' or options['offload'] == 'none': # even if the user select 'NO' we need to add the toleration for the virtual-kubelet and explicit the 'none' accelerator. Probably the virtual-node.interlink/no-schedule should be removed
            self.tolerations = [
                {
                    "key": "accelerator",
                    "operator": "Equal",
                    "value": "none",
                    "effect": "NoSchedule"
                },
                {
                    "key": "virtual-node.interlink/no-schedule",
                    "operator": "Exists",
                    "effect": "NoSchedule"
                }
            ]

        self.services_enabled = True
        self.extra_labels = { "app": "jupyterhub",  "component": "hub", "release": "helm-jhub-release"}

        return options

    def get_service_manifest(self, owner_reference):
        """
        Make a service manifest for dns.
        """
        labels = self._build_common_labels(self._expand_all(self.extra_labels))
        annotations = self._build_common_annotations(
            self._expand_all(self.extra_annotations)
        )

        from kubernetes_asyncio.client.models import ( V1ObjectMeta, V1Service, V1ServiceSpec, V1ServicePort)

        metadata = V1ObjectMeta(
            name=self.pod_name,
            annotations=annotations,
            labels=labels,
            owner_references=[owner_reference],
        )

        service = V1Service(
            kind='Service',
            metadata=metadata,
            spec=V1ServiceSpec(
                type='ClusterIP',
                ports=[V1ServicePort(name='http', port=self.port, target_port=self.port)],
                selector={ "app": "jupyterhub",  "component": "hub", "release": "helm-jhub-release"}
            ),
        )

        return service

    @property
    def environment(self):
        # dciangot: create an ssh connection on a random port

        environment = {
                "JHUB_HOST": jhub_host,
                "SSH_PORT": "31022",
                "FWD_PORT": f"{self.port}",
                "JUPYTERHUB_API_URL": jhub_api_url,
                "JUPYTERHUB_ACTIVITY_URL": f"{jhub_api_url}/users/{self.user.name}/activity",
                "JUPYTERHUB_SERVICE_URL": jhub_host
                }

        return environment

    @property
    def node_selector(self):

        node_selector = { "kubernetes.io/role": "agent",
                            "beta.kubernetes.io/os": "linux",
                            "type" : "virtual-kubelet"}

        node_selector.update({"kubernetes.io/hostname" : self.map_node_gpu[self.user_options.get('offload')]["hostname"]})

        if self.user_options.get('offload')=="N":
            node_selector = {}

        return node_selector

    @property
    def volume_mounts(self):
        return [
            {
                'name': f'{self.user.name}-volume',
                'mountPath': '/home/jovyan'
            },
        ]

    @property
    def volumes(self):
        return [
            {
                'name': f'{self.user.name}-volume',
                'hostPath': {
                    'path': '/opt/workspace/persistent-storage',
                    'type': 'DirectoryOrCreate',
                },
            },
        ]


c.JupyterHub.spawner_class = CustomSpawner
c.KubeSpawner.cmd = [" "]
c.KubeSpawner.args = [" "]
c.KubeSpawner.privileged = True
c.KubeSpawner.allow_privilege_escalation = True
c.KubeSpawner.extra_pod_config = {
    "automountServiceAccountToken": True,
        }
        
c.KubeSpawner.init_containers = []

c.KubeSpawner.debug = True

c.KubeSpawner.services_enabled = True
c.KubeSpawner.extra_labels = { "app": "jupyterhub",  "component": "hub", "release": "helm-jhub-release"}

c.KubeSpawner.extra_container_config = {
    "securityContext": {
            "privileged": True,
            "capabilities": {
                        "add": ["SYS_ADMIN"]
                    }
        }
}

c.KubeSpawner.http_timeout = 60
c.KubeSpawner.start_timeout = 60
c.KubeSpawner.notebook_dir = "/home/jovyan"

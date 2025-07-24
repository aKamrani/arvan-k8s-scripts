# Save your multi-YAML as manifest.yaml first!

import yaml
from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException

# Load kube config (uses current context)
config.load_kube_config()

# Path to your combined YAML file
manifest_path = "manifest.yaml"
namespace = "delta"  # Change as needed

# Helper to pick correct API for each kind
def get_api(kind, api_version):
    if kind == "Deployment":
        return client.AppsV1Api()
    elif kind == "Service":
        return client.CoreV1Api()
    elif kind == "Secret":
        return client.CoreV1Api()
    elif kind == "Ingress":
        # v1.19+ uses networking.k8s.io/v1
        return client.NetworkingV1Api()
    else:
        raise NotImplementedError(f"No support for kind: {kind}")

def get_create_func(kind):
    return {
        "Deployment": "create_namespaced_deployment",
        "Service": "create_namespaced_service",
        "Secret": "create_namespaced_secret",
        "Ingress": "create_namespaced_ingress"
    }[kind]

def get_replace_func(kind):
    return {
        "Deployment": "replace_namespaced_deployment",
        "Service": "replace_namespaced_service",
        "Secret": "replace_namespaced_secret",
        "Ingress": "replace_namespaced_ingress"
    }[kind]

def get_read_func(kind):
    return {
        "Deployment": "read_namespaced_deployment",
        "Service": "read_namespaced_service",
        "Secret": "read_namespaced_secret",
        "Ingress": "read_namespaced_ingress"
    }[kind]

with open(manifest_path, "r") as f:
    docs = list(yaml.safe_load_all(f))

for doc in docs:
    if not doc:
        continue
    kind = doc.get("kind")
    meta = doc.get("metadata", {})
    name = meta.get("name")
    api_version = doc.get("apiVersion", "v1")
    
    # Pick API group
    api = get_api(kind, api_version)
    create_func = getattr(api, get_create_func(kind))
    replace_func = getattr(api, get_replace_func(kind))
    read_func = getattr(api, get_read_func(kind))
    
    try:
        # Try to read to check for existence
        obj = read_func(name=name, namespace=namespace)
        # Exists: attempt replace
        print(f"Replacing {kind} {name} ...")
        # For some kinds (like Service), immutable fields (clusterIP etc) will cause errors.
        try:
            replace_func(name=name, namespace=namespace, body=doc)
            print(f"Replaced {kind} {name}")
        except ApiException as e:
            print(f"Error replacing {kind} {name}, will try patch: {e}")
            # For immutable fields, last resort: Patch (less strict)
            try:
                api.patch_namespaced_service(name=name, namespace=namespace, body=doc)
                print(f"Patched {kind} {name}")
            except Exception as e2:
                print(f"Still failed to patch {kind} {name}: {e2}")
    except ApiException as e:
        # Doesn't exist: create new
        print(f"Creating {kind} {name} ...")
        try:
            create_func(namespace=namespace, body=doc)
            print(f"Created {kind} {name}")
        except ApiException as e2:
            print(f"Error creating {kind} {name}: {e2}")

from kubernetes import client, config
import yaml

namespace = "<NAMESPACE_NAME>"
deployment_name = "<APP_NAME>"

config.load_kube_config()

apps = client.AppsV1Api()
core = client.CoreV1Api()
networking = client.NetworkingV1Api()

def clean_deployment(dep):
    # Only retrain the fields you want
    return {
        "apiVersion": dep["api_version"],
        "kind": dep["kind"] or "Deployment",
        "metadata": {
            "annotations": dep["metadata"].get("annotations", {}),
            "generation": dep["metadata"].get("generation"),
            "labels": dep["metadata"].get("labels", {}),
            "name": dep["metadata"]["name"]
        },
        "spec": dep["spec"]
    }

def clean_service(svc):
    print(svc)
    return {
        "kind": svc["kind"] or "Service",
        "metadata": {
            "annotations": svc["metadata"].get("annotations", {}),
            "labels": svc["metadata"].get("labels", {}),
            "name": svc["metadata"]["name"]
        },
        "spec": svc["spec"]
    }

def clean_ingress(ing):
    return {
        "kind": ing["kind"] or "Ingress",
        "metadata": {
            "generation": ing["metadata"].get("generation"),
            "name": ing["metadata"]["name"]
        },
        "spec": ing["spec"]
    }

def clean_secret(sec):
    return {
        "apiVersion": sec.get("api_version", "v1"),
        "kind": sec["kind"] or "Secret",
        "metadata": {"name": sec["metadata"]["name"]},
        "data": {k: v for k, v in sec.get("data", {}).items()},
        "type": sec.get("type", "Opaque"),
    }

def main():
    # ----- FETCH DEPLOYMENT -----
    dep_obj = apps.read_namespaced_deployment(deployment_name, namespace)
    dep = dep_obj.to_dict()
    label_selector = ",".join([f"{k}={v}" for k, v in dep["metadata"]["labels"].items()]) if dep["metadata"].get("labels") else ""
    
    # ----- DISCOVER SERVICES -----
    services = core.list_namespaced_service(namespace, label_selector=label_selector).items
    # Deduplicate via name
    service_names = {svc.metadata.name for svc in services}

    # ----- DISCOVER INGRESS -----
    ingresses = networking.list_namespaced_ingress(namespace).items
    ingress_names = set()
    for ing in ingresses:
        if any(
            rule.http and any(
                path.backend and path.backend.service and path.backend.service.name in service_names
                for path in rule.http.paths
            ) for rule in (ing.spec.rules or [])
        ):
            ingress_names.add(ing.metadata.name)
        elif ing.metadata.labels and any(dep["metadata"]["labels"].get(k) == v for k, v in ing.metadata.labels.items()):
            ingress_names.add(ing.metadata.name)

    # ----- DISCOVER SECRETS -----
    secret_names = set()
    template_spec = dep["spec"]["template"]["spec"]
    for volume in template_spec.get("volumes", []):
        secret_info = volume.get("secret")
        if secret_info and secret_info.get("secret_name"):
            secret_names.add(secret_info["secret_name"])

    # ----- OUTPUT -----
    docs = []
    docs.append(clean_deployment(dep))

    for svc in services:
        docs.append(clean_service(svc.to_dict()))

    for ing in ingresses:
        if ing.metadata.name in ingress_names:
            docs.append(clean_ingress(ing.to_dict()))

    for secret_name in secret_names:
        try:
            sec = core.read_namespaced_secret(secret_name, namespace)
            docs.append(clean_secret(sec.to_dict()))
        except client.exceptions.ApiException as e:
            print(f"Warning: Secret '{secret_name}' not found: {str(e)}")

    # YAML output
    for doc in docs:
        print("---")
        print(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False).strip())

if __name__ == "__main__":
    main()

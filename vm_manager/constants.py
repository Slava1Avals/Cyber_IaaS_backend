VM_IMAGE_CATALOG = {
    "default": {
        "docker_image": "ubuntu:22.04",
        "run_cmd": ["sleep", "infinity"],
        "cpu_cores": 1,
        "ram_mb": 512,
        "disk_gb": 4,
        "network_mbps": 100,
    },
}


VM_STATUS_ACTIVE = {"starting", "running", "stopping", "stopped", "restarting", "failed"}

# SUFRA OS on Kubernetes

Same image as the Fly.io deploy (`../Dockerfile`), same behaviour: the first boot
seeds `/data/nova.db` from the build snapshot, later boots keep the volume.

```bash
cd ..                                   # sufra-os
sh deploy/prepare.sh                    # builds deploy/seed.db, as for Fly
docker build -t ghcr.io/<you>/sufra-os:1 .
docker push ghcr.io/<you>/sufra-os:1
# edit k8s/kustomization.yaml: newName / newTag, and k8s/ingress.yaml: host
kubectl apply -k k8s
kubectl -n sufra rollout status deploy/sufra-os
kubectl -n sufra port-forward svc/sufra-os 8123:80      # http://localhost:8123
```

Rules that matter
- **One replica only.** SQLite + in-process scheduler (see deployment.yaml).
- Change the staff PINs before exposing it; the seed ships demo PINs.
- Back up the volume (`kubectl -n sufra exec deploy/sufra-os -- sqlite3 /data/nova.db ".backup /data/backup.db"`), or snapshot the PVC.
- SUFRA 360 reaches this service at `http://sufra-os.sufra.svc.cluster.local`.

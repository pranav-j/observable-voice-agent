# 0009: Deploying the demo

- **Status:** accepted
- **Date:** 2026-10-13

## Context

The project needs a public demo: a page where anyone can start a call. Expected use is a handful of calls a day, rarely two at once. The budget is a few dollars a month beyond the LLM, which costs about $0.0003 per minute of call with local speech.

A voice agent has parts that scale differently:

- LiveKit, the media server, needs public UDP and TCP ports and stable connections.
- Agent workers need CPU for every concurrent call. Each call's process holds Whisper, Kokoro and the turn detector, about 600 to 850 MB.
- The API is small and stateless.
- Postgres holds state.
- The web app is static files.

At real scale these would be deployed separately. At demo scale, separating them multiplies cost and moving parts for nothing.

## Decision

**One EC2 instance, built the way the larger setup would be.**

- **Where:** a `c7g.xlarge` (4 vCPU, 8 GiB, ARM) in `ap-south-1`, $0.0982 an hour on demand. Every native dependency ships Linux ARM wheels.
- **What runs:** `docker compose` with Caddy, the API, the agent worker, LiveKit, Postgres and Phoenix (`deploy/compose.yaml`).
- **Images:**
  - Two images, both arm64. The app image runs both the API and the worker. The web image is the built app served by Caddy.
  - Base images are pinned by digest, Python packages by `uv.lock`, and the Kokoro files by checksum. Whisper's weights are fetched at build time.
  - Each image is tagged with its commit and pushed to ECR, where tags can't be overwritten. What runs is exactly what was evaluated, models included.
- **Infrastructure as code:** Terraform (`deploy/terraform`) creates the registry, the instance role, the security group, the instance and its address. `make deploy-destroy` removes all of it.
- **Secrets:** stored in SSM Parameter Store as SecureStrings. The instance reads them at start into a root-only file. They never pass through Terraform state or the repository.
- **Access:** no SSH and no port 22. Shell access, and the Phoenix UI through a port forward, go through Session Manager.
- **Network:**
  - HTTPS from Caddy, with a Let's Encrypt certificate for `<address>.sslip.io`, since there's no domain.
  - LiveKit signalling goes through Caddy. Media uses one UDP port, with a TCP fallback.
- **Releases:**
  - `make deploy-images` builds and pushes the commit.
  - `make deploy-release TAG=...` records the tag in SSM, pushes the deploy files, restarts the stack, and waits until the site answers.
  - The worker gets five and a half minutes to finish calls in progress before it's stopped.
- **Cost guards:**
  - The call limits from `docs/adr/0008-demo-limits.md`: 5 calls per address per hour, 40 a day, 5 minutes each.
  - An optional budget alarm.
  - `make demo-stop` between demos.
- **Calls nobody answers:** a worker that's out of CPU tells LiveKit it's full, and LiveKit then doesn't send it the call. This happened once in the local eval runs, when the test suite was running on the same machine. The page now gives up after 20 seconds with a "busy" message, rather than leaving the caller in silence.
- **Recordings:** a notice on the page asks callers to use made-up details. Recordings older than 7 days are deleted daily.

## The production shape, and when to move

| Part | Demo | Production |
|---|---|---|
| Media | LiveKit on the instance | LiveKit on its own instances, or LiveKit Cloud |
| Workers | One compose service | An autoscaling group, scaled on worker load. Workers pull jobs from LiveKit, so adding workers adds capacity with no load balancer. They drain calls before scale-in. |
| Speech models | In every worker process | A shared GPU inference service, or hosted speech |
| API | Compose service | Containers behind a load balancer |
| Database | Postgres container | RDS with backups |
| Web | Caddy on the instance | S3 and CloudFront |
| Releases | From a laptop | CI builds the images, the eval gate passes, then a role assumed through GitHub OIDC rolls out |
| Terraform state | Local file | S3 with locking |
| Recordings | Instance disk, 7 days | S3 with a lifecycle rule, and a consent step |

Move when any of these becomes true:

- More concurrent calls than one instance's CPU can take. A load test with the simulated callers would find that number before real callers do.
- An uptime requirement, since one instance is one point of failure.
- Speech models that need a GPU.

## Alternatives

- **LiveKit Cloud for media, plus a small instance for the workers.** It removes the hardest part of self-hosting, the UDP ports and TLS for WebRTC, and has a free tier. It adds a third-party service, and the demo would depend on its quotas. A good next step if self-hosted media gives trouble.
- **ECS on Fargate.** Fargate fits the API and workers, but WebRTC media needs UDP ports on a stable address, which is awkward there. It would split the stack across two kinds of compute for little gain at this size.
- **Kubernetes.** Far more to run than a demo needs.
- **A larger or GPU instance.** Not needed for one or two calls at a time on CPU models.

## Consequences

- One instance is a single point of failure, and restarting it ends calls in progress.
- While stopped, the instance costs only its disk and its address. AWS charges for a public IPv4 address even when it isn't attached to a running instance.
- The hostname depends on sslip.io, a free DNS service, to map the name to the address.
- Terraform state is a local file. It holds resource ids, not secrets, but losing it means importing or deleting the resources by hand.
- The budget alarm filters on the `project` tag, which has to be activated as a cost allocation tag in the billing console before it counts anything.

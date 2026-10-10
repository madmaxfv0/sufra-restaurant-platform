# Putting SUFRA 360 on a permanent public link

Two apps go up together on Fly.io, because SUFRA 360 holds no data of its
own - every table, booking and menu item comes from SUFRA OS.

| App | Link | Who uses it |
|---|---|---|
| SUFRA 360 | `https://sufra-360.fly.dev` | guests |
| SUFRA OS | `https://sufra-os.fly.dev` | staff |

## Once

1. Create an account at fly.io (it asks for a card).
2. Install the command line tool: https://fly.io/docs/flyctl/install/
3. `fly auth login`

## Every deploy

```bash
sh sufra-360/deploy/deploy_fly.sh
```

If Fly says a name is taken, pick your own:
`sh deploy/deploy_fly.sh my-sufra-360 my-sufra-os`

The first run uploads about 600 MB of 3D assets, so allow several minutes.

## What to know

- **The database starts as a copy of the local `sufra-os/nova.db`**, taken at the
  first deploy. After that the hosted database is the real one: it lives on
  a Fly volume and later deploys do not touch it. Bookings made locally
  after that point do not appear online, and the other way round.
- **Change the staff PINs before sharing the staff link.** SUFRA OS will be
  reachable from the internet, and the PINs it was seeded with are 4 digits.
- **Back up the volume.** Fly keeps daily snapshots for 5 days by default;
  `fly volumes snapshots list <volume-id>` shows them.
- **Your own domain** (e.g. `book.sufra.az`): `fly certs add book.sufra.az
  -a sufra-360`, then add the DNS record it prints.
- Logs: `fly logs -a sufra-360` / `fly logs -a sufra-os`.

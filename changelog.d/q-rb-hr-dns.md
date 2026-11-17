### Bug fixes

- A job that blocks and stops because the agent of Harden-Runner took itself away again after one failed lookup of a host that it allows now says so: its annotation names the host and that it was no outage, instead of an agent that didn't start, and the job stops at once instead of waiting half a minute for a status that can't come. The bots still run such a job again, and the fix of the cause belongs in Harden-Runner's agent. A workflow of the project with a job that blocks copies the step *Make sure that Harden-Runner blocks* from `.github/workflows/welcome.yml` again.

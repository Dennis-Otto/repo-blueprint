### Bug fixes

- **The Rollout no longer takes a release for none in the hour that repeats when the clocks go back:** GitHub dated the job that published v1.3.0 before the start of its run, in the hour that repeats when the clocks of the US go back, and its list of the jobs of the latest attempt left that job out. The Rollout then wrote that the run made no release, ended green and updated no repository. It now asks for the jobs of all attempts and takes the last attempt's.

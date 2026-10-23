### Bug fixes

- **The recording of `copier copy` renews itself again:** since 1.0.0, Copier says five lines before its questions, and the picture bot of the website and the README timed out at the license, because the wait it used there reads only the first screen of the terminal. From the license on, each answer now waits for the line of the cursor, and a test keeps every other wait on that first screen.

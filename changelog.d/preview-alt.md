### Bug fixes

- **The home page of a website keeps the text of its preview picture:** since the home page shows the designed preview of the repository, it also dropped `og:image:alt`, the text that describes the picture to people who can't see it, so a project's check of its website failed. The home page now keeps `og:image:alt` and `twitter:image:alt`.

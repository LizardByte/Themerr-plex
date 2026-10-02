group "default" {
  targets = ["image"]
}

target "image" {
  context = "."
  dockerfile = "Dockerfile"
  platforms = ["linux/amd64", "linux/arm64"]
}

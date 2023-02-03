import pkg_resources


def version():
    return pkg_resources.get_distribution("abstra-runtimes").version


# import requests

# def check_version():
#     try:
#         __version__ = version()
#         libs = requests.get(
#             "https://hackerforms-api.abstra.cloud/public/abstra-pypi-packages"
#         ).json()
#         hackerforms = list(filter(lambda lib: lib["name"] == "hackerforms", libs))[0]
#         if hackerforms["version"] != __version__ and __version__ != "0.0.0":
#             print("You are using an outdated version of hackerforms.")
#             print(
#                 "Please update your library using the following command: pip install hackerforms=="
#                 + hackerforms["version"]
#             )
#     except Exception as e:
#         pass


if __name__ == "__main__":
    print(version())

import pkg_resources


def version():
    return pkg_resources.get_distribution("abstra-runtimes").version


if __name__ == "__main__":
    print(version())

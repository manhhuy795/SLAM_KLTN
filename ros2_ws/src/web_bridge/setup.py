from glob import glob
from setuptools import find_packages, setup


package_name = "web_bridge"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="huy",
    maintainer_email="huy@example.com",
    description="ROS 2 to WRMS FastAPI bridge.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "web_bridge = web_bridge.web_bridge_node:main",
        ],
    },
)

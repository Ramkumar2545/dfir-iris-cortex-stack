from setuptools import setup, find_packages

setup(
    name="iris-cortex-module-v3",
    version="3.0.0",
    description="IRIS Cortex Module v3 — native requests, Cortex 3.x/4.x compatible",
    author="Ramkumar2545",
    url="https://github.com/Ramkumar2545/dfir-iris-cortex-stack",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28",
        "jinja2>=3.0",
        "urllib3>=1.26",
        "iris-module-interface>=1.2",
    ],
    python_requires=">=3.9",
    entry_points={
        "iris_module": [
            "IrisCortexModuleV3 = iris_cortex_module_v3.IrisCortexModuleV3:IrisCortexModuleV3",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
)

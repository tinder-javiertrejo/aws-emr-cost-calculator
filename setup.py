# coding=utf-8
import setuptools

setuptools.setup(
    name='aws-emr-cost-calculator',
    version='0.0.1',
    scripts=['aws-emr-cost-calculator'],
    author="Marko Baštovanović",
    author_email="marko.bast@gmail.com",
    description="Utility package to calculate cost of an AWS EMR cluster",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/marko-bast/emr-cost-calculator",
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.7',
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=['requests[security]>=2.18.3',
                      'retrying',
                      'boto3>=1.9',
                      'docopt']
)

#!/usr/bin/env python

import os
import sys
import json
import yaml
import shutil
import subprocess

import hurl

def load_stack(app_dir):
    """ Load stack description from an app's directory """
    for filename in ['Stackfile', 'stackfile', 'dotcloud.yml', 'dotcloud_build.yml']:
        filepath = os.path.join(app_dir, filename)
        if os.path.exists(filepath):
            return dict(yaml.load(file(filepath)))

def get_service_root(app_dir, service):
    """ Return the root directory a service (as defined by its "approot" property in the stackfile) """
    return os.path.join(app_dir, load_stack(app_dir)[service].get("approot", "."))

def get_service_buildscript(app_dir, service):
    """ Return the path to a service's build script (as defined by its "buildscript" property in the stackfile). """
    return mkpath((app_dir, load_stack(app_dir)[service]["buildscript"]))

def get_remote_buildpack(buildpack):
    """ Download a buildpack from a remote location, and return the local path it was downloaded to. """
    url = hurl.parse(buildpack)
    dl_cache = '/tmp/stackbrew'
    if (url.get('proto') == 'http' and url.get('path').endswith('.git')) or (url.get('proto') == 'git'):
        dl_path = '{dl_cache}/{host}/{path}'.format(dl_cache=dl_cache, **url)
        if os.path.exists(dl_path):
            shutil.rmtree(dl_path)
        os.makedirs(dl_path)
        subprocess.call('git clone {buildpack} {dl_path}'.format(**locals()), shell=True)
        return dl_path
    return None


def get_local_buildpack(buildpack):
    """ Search for `buildpack` using the BUILDPACK_PATH environment variable.
        Default to the litteral filesystem path.
    """
    if os.path.exists(buildpack):
        return buildpack
    for buildpack_dir in os.environ.get("BUILDPACK_PATH", "").split(":"):
        path = os.path.join(buildpack_dir, buildpack)
        print "Checking for {path}".format(path=path)
        if os.path.exists(path):
            return path
    return None


def get_buildpack_dir(buildpack):
    """ Search for a buildpack using all available methods, and return the path to a local directory. """
    remote = get_remote_buildpack(buildpack)
    if remote:
        return remote
    local = get_local_buildpack(buildpack)
    if local:
        return local
    if not dir:
        raise KeyError("No such buildpack: {buildpack}".format(**locals()))


def build_service(service_name, build_dir, buildpack):
    """ Build the service in-place at `build_dir` using `buildpack`.
        `service_name` is provided as a convenience.
    """
    buildpack_dir = get_buildpack_dir(buildpack)
    cache_dir = "{buildpack}/_cache".format(buildpack=buildpack_dir)
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    print "['{build_dir}'] building service '{service_name}' with buildpack '{buildpack}' and cache '{cache_dir}'".format(**locals())
    subprocess.call(["{buildpack}/bin/compile".format(buildpack=buildpack_dir), build_dir, cache_dir])
    release_script = "{buildpack}/bin/release".format(buildpack=buildpack_dir)
    if not os.path.exists(release_script):
        return {}
    return dict(yaml.load(subprocess.Popen([release_script, build_dir], stdout=subprocess.PIPE).stdout.read()))

def mkpath(path):
    if type(path) == str:
        return path
    return os.path.join(*path)

def copy(src, dst):
    """ Copy a directory from `src` to `dst`. """
    src = mkpath(src)
    dst = mkpath(dst)
    print "Copying {src} to {dst}".format(**locals())
    shutil.copytree(src, dst)

def mkfile(path, x=False, **kw):
    """ Create a file, and the enclosing directory if it doesn't exist.
        Extra keywords are passed to the file constructor.
    """
    path = mkpath(path)
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = file(path, "w", **kw)
    if x:
        # FIXME: this is me being too lazy to look up how to do `chmod +x` cleanly in python
        os.chmod(path, 0700)
    return f


def getfile(path):
    return file(mkpath(path))


def cmd_build(source_dir, build_dir):
    """ Build the application source code at `source_dir` into `build_dir`.
        The build will fail if build_dir alread exists.
    """
    os.makedirs(build_dir)
    config = {}
    for (service, config) in load_stack(source_dir).items():
        buildpack = config["type"]
        print "{service} -> {buildpack}".format(service=service, buildpack=buildpack)
        service_build_dir = "{build_dir}/{service}".format(**locals())
        copy(source_dir, service_build_dir)
        config[service] = build_service(service, service_build_dir, buildpack)
    file("{build_dir}/deploy.json".format(**locals()), "w").write(json.dumps(config, indent=1))

def cmd_info(source_dir):
    """ Dump the contents of an application stack. """
    print json.dumps(load_stack(source_dir), indent=1)

def cmd_convert(source_dir, service, dest):
    """ Extract a custom service from an application, and convert it to a buildpack. """
    stack = load_stack(source_dir)
    if stack[service].get("type", "custom") != "custom":
        raise Exception("Only custom services can be converted to a buildpack.")
    # Copy service directory
    copy(
        (source_dir, stack[service].get("approot", ".")),
        dest)
    # Copy build script to bin/compile
    print "Copying build script to bin/compile"
    buildscript_src = file(get_service_buildscript(source_dir, service))
    buildscript_dest = mkfile((dest, "bin/compile"))
    buildscript_dest.write(buildscript_src.read())
    # Encapsulate relevant service config in a bin/release
    print "Copying config to bin/release"
    mkfile((dest, "bin/release"), x=True).write(
"""#!/bin/sh

###
### This release script was generated by stackbrew,
### using configuration from a dotCloud custom service.
###
### See http://github.com/shykes/stackbrew for details.
###

cat <<EOF
{config}
EOF
""".format(config = yaml.dump(stack[service]))
    )

def cmd_buildscript(source_dir, service):
    print file(get_service_buildscript(source_dir, service)).read()

def cmd_services(source_dir):
    for service in sorted(load_stack(source_dir)):
        print service

def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    eval("cmd_{cmd}".format(cmd=cmd))(*args)

if __name__ == '__main__':
    main()

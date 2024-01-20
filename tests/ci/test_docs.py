# standard imports
import os
import platform
import shutil
import subprocess

# lib imports
import pytest


doc_matrix = [
    ('html', os.path.join('html', 'index.html')),
    ('epub', os.path.join('epub', 'Themerr-plex.epub')),
]


@pytest.mark.parametrize('doc_type, file_name', doc_matrix)
def test_make_docs(doc_type, file_name):
    """Test building sphinx docs"""
    # remove existing build directory
    build_dir = os.path.join(os.getcwd(), 'docs', 'build')
    if os.path.isdir(build_dir):
        shutil.rmtree(path=build_dir)

    print('Building {} docs'.format(doc_type))
    result = subprocess.check_call(
        args=['make', doc_type],
        cwd=os.path.join(os.getcwd(), 'docs'),
        shell=True if platform.system() == 'Windows' else False,
    )
    assert result == 0, 'Failed to build {} docs'.format(doc_type)

    # ensure docs built
    assert os.path.isfile(os.path.join(build_dir, file_name)), '{} docs not built'.format(doc_type)


@pytest.mark.parametrize('doc_type, file_name', doc_matrix)
def test_dummy_file(doc_type, file_name):
    """Test building sphinx docs with known warnings"""
    # create a dummy rst file
    dummy_file = os.path.join(os.getcwd(), 'docs', 'source', 'dummy.rst')

    # write test to dummy file, creating the file if it doesn't exist
    with open(dummy_file, 'w+') as f:
        f.write('Dummy file\n')
        f.write('==========\n')

    # ensure CalledProcessError is raised
    with pytest.raises(subprocess.CalledProcessError):
        test_make_docs(doc_type=doc_type, file_name=file_name)

    # remove the dummy rst file
    os.remove(dummy_file)


def test_rstcheck():
    """Test rstcheck"""
    # get list of all the rst files in the project (skip venv and Contents/Libraries)
    rst_files = []
    for root, dirs, files in os.walk(os.getcwd()):
        for f in files:
            if f.lower().endswith('.rst') and 'venv' not in root and 'Contents/Libraries' not in root:
                rst_files.append(os.path.join(root, f))

    assert rst_files, 'No rst files found'

    # run rstcheck on all the rst files
    for rst_file in rst_files:
        print('Checking {}'.format(rst_file))
        result = subprocess.check_call(['rstcheck', rst_file])
        assert result == 0, 'rstcheck failed on {}'.format(rst_file)

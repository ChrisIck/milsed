#!/usr/bin/env python
'''MILSED utilities'''

import os
import subprocess
import h5py
from librosa.util import find_files
import jams
import pandas as pd
import scipy
import numpy as np


def save_h5(filename, **kwargs):
    '''Save data to an hdf5 file.

    Parameters
    ----------
    filename : str
        Path to the file

    kwargs
        key-value pairs of data

    See Also
    --------
    load_h5
    '''
    with h5py.File(filename, 'w') as hf:
        hf.update(kwargs)


def load_h5(filename):
    '''Load data from an hdf5 file created by `save_h5`.

    Parameters
    ----------
    filename : str
        Path to the hdf5 file

    Returns
    -------
    data : dict
        The key-value data stored in `filename`

    See Also
    --------
    save_h5
    '''
    data = {}

    def collect(k, v):
        if isinstance(v, h5py.Dataset):
            data[k] = v.value

    with h5py.File(filename, mode='r') as hf:
        hf.visititems(collect)

    return data


def base(filename):
    '''Identify a file by its basename:

    /path/to/base.name.ext => base.name

    Parameters
    ----------
    filename : str
        Path to the file

    Returns
    -------
    base : str
        The base name of the file
    '''
    return os.path.splitext(os.path.basename(filename))[0]


def get_ann_audio(directory):
    '''Get a list of annotations and audio files from a directory.

    This also validates that the lengths match and are paired properly.

    Parameters
    ----------
    directory : str
        The directory to search

    Returns
    -------
    pairs : list of tuples (audio_file, annotation_file)
    '''

    audio = find_files(directory)
    annos = find_files(directory, ext=['jams', 'jamz'])

    paired = list(zip(audio, annos))

    if (len(audio) != len(annos) or
       any([base(aud) != base(ann) for aud, ann in paired])):
        raise RuntimeError('Unmatched audio/annotation '
                           'data in {}'.format(directory))

    return paired


def git_version():
    '''Return the git revision as a string

    Returns
    -------
    git_version : str
        The current git revision
    '''
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(['git', 'rev-parse', '--short', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION


def increment_version(filename):
    '''Increment a model version identifier.

    Parameters
    ----------
    filename : str
        The file containing the model version

    Returns
    -------
    model_version : str
        The new model version.
        This version will also be written out to `filename`.
    '''

    gv = git_version()
    iteration = 0

    try:
        with open(filename, 'r') as fd:
            line = fd.read()
            old_gv, old_iteration = line.split('.', 2)
            old_iteration = int(old_iteration)

            if old_gv == gv:
                iteration = old_iteration + 1
    except FileNotFoundError:
        pass

    version = '{}.{}'.format(gv, iteration)

    with open(filename, 'w') as fd:
        fd.write(version)

    return version


def create_dcase_jam(fid, labelfile, duration=10.0, weak=False):

    # Create jam
    jam = jams.JAMS()

    # Create annotation
    ann = jams.Annotation('tag_open')
    # duration = sox.file_info.duration(audiofile)
    ann.duration = duration

    # Get labels from CSV file
    fid_ = fid[1:]
    labeldf = pd.read_csv(labelfile, header=None, sep='\t')
    labeldf.columns = ['filename', 'start_time', 'end_time', 'label']
    labeldf = labeldf[labeldf['filename'].str.contains(fid_)]
#    assert len(labeldf) > 0

    # Add tag for each label
    for idx, row in labeldf.iterrows():
        if weak:
            ann.append(time=0, duration=duration, value=row.label,
                       confidence=1.0)
        else:
            if row.end_time <= row.start_time:
                continue
            ann.append(time=row.start_time,
                       duration=(row.end_time - row.start_time),
                       value=row.label,
                       confidence=1.0)

    # Fill file metadata
    jam.file_metadata.title = fid
    jam.file_metadata.release = '1.0'
    jam.file_metadata.duration = duration
    jam.file_metadata.artist = ''

    # Fill annotation metadata
    ann.annotation_metadata.version = '1.0'
    ann.annotation_metadata.corpus = 'DCASE 2017 Task 4'
    ann.annotation_metadata.data_source = 'AudioSet'
    ann.annotation_metadata.annotation_tools = 'reference'

    # Add annotation to jam
    jam.annotations.append(ann)

    # Return jam
    return jam


def interpolate_prediction(sample_pred, duration, interp_size):
    '''
    Interpolate model predictions (likelihoods over time).

    Given prediction for single sample 'sample_pred' with shape (1, n_frames,
    n_classes), the time 'duration' (in seconds) the prediction corresponds to,
    and the desired number of interpolated frames 'interp_size', this will
    return interpolated predictions with shape (1, interp_size, n_classes).
    Uses linear interpolation.

    Parameters
    ----------
    sample_pred : np.ndarray
        Prediction matrix (likeihood) with shape (1, n_frames, n_classes)
    duration : float
        Time duration in seconds that sample_pred corresponds to.
    interp_size : int
        Desired number of output frames in the interpolated prediction.

    Returns
    -------

    '''
    pred = sample_pred[0]
    interp = scipy.interpolate.interp1d(
        np.arange(pred.shape[0]) / float(pred.shape[0]) * duration, pred.T,
        kind='linear', bounds_error=False, fill_value=pred[-1])

    pred_interp = interp(np.arange(interp_size) / float(interp_size) * duration).T
    pred_interp = np.expand_dims(pred_interp, 0)

    return pred_interp




#!/usr/bin/env python3
import pathlib
import click
import re
import iridauploader.config as _config
import iridauploader.core as core
from iridauploader.model import Project
from iridauploader.core import api_handler
import logging
import datetime
import os
import configparser
import tempfile
import atexit


def get_config_value(config, section, key, env_var, prompt_msg, hide_input=False):
    """Helper function to get a config value from file, env, or prompt."""
    if section in config and key in config[section]:
        return config[section][key]
    value = os.environ.get(env_var)
    if not value:
        value = click.prompt(prompt_msg, hide_input=hide_input)
    return value

def initialize_irida_api(config_file: str = None):
    """
    Initialize the IRIDA API from the configuration file, environment variables, or interactive prompt.
    Returns the API instance and the path to the temporary config file.
    """
    config = configparser.ConfigParser()
    if config_file and os.path.exists(config_file):
        config.read(config_file)

    settings = {
        "base_url": get_config_value(
            config, "Settings", "base_url", "IRIDA_BASE_URL", "Enter IRIDA base URL"
        ),
        "client_id": get_config_value(
            config, "Settings", "client_id", "IRIDA_CLIENT_ID", "Enter IRIDA client ID"
        ),
        "client_secret": get_config_value(
            config,
            "Settings",
            "client_secret",
            "IRIDA_CLIENT_SECRET",
            "Enter IRIDA client secret",
            hide_input=True,
        ),
        "username": get_config_value(
            config, "Settings", "username", "IRIDA_USERNAME", "Enter IRIDA username"
        ),
        "password": get_config_value(
            config,
            "Settings",
            "password",
            "IRIDA_PASSWORD",
            "Enter IRIDA password",
            hide_input=True,
        ),
        "timeout_multiplier": get_config_value(
            config, "Settings", "timeout", "IRIDA_TIMEOUT", "Enter API timeout"
        ),
    }

    _api = api_handler._initialize_api(**settings)

    # Create a temporary config file
    temp_config = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".conf")
    temp_config_path = temp_config.name

    config["Settings"] = settings
    config.write(temp_config)
    temp_config.close()

    # Schedule the temporary file for deletion when the script exits
    atexit.register(os.unlink, temp_config_path)

    return _api, temp_config_path


# @click.command()
# @click.option('--project_description', help='Project description')
# @click.option('--config_file', default='config.conf', help='Config file')
# @click.argument('name')
# @click.argument('path', default=os.getcwd())
def create_project(name, config_file, project_description=None):
    """
    Create a project in IRIDA.

    Args:
        name (str): The name of the project.
        config_file (str): The path to the configuration file.
        project_description (str, optional): The description of the project. If not provided, a default description
            will be used.

    Returns:
        int: The identifier of the created project.

    Raises:
        Exception: If an error occurs during project creation.
    """
    # _config.set_config_file(config_file)
    # _config.setup()
    if project_description is None:
        project_description = f"Created on {datetime.date.today()} by BOT"
    try:
        # _api = api_handler.initialize_api_from_config()
        _api, _ = initialize_irida_api(config_file)
        projects_list = _api.get_projects()
        existed_project = [prj.id for prj in projects_list if prj.name == name]
        if len(existed_project) == 0:
            new_project = Project(name, project_description)
            created_project = _api.send_project(new_project)
            logging.info(f"Created project {name} - {created_project['resource']['identifier']}")
            project_id = created_project['resource']['identifier']
            return project_id
        else:
            logging.warning(f"Project(s) {name} is existed")
            logging.info(existed_project)
            return existed_project[0]
    except Exception as e:
        raise e


@click.command()
@click.option("--pid", default=None, help="Project ID")
@click.option("--name", default=None, help="Project Name")
@click.option("--pe/--se", default=False, help="Paired-End reads?")
@click.option("--sort/--no-sort", default=False, help="Sort samples [Experiment]")
@click.option("--pattern", default="*_R1_001.fastq.gz", help="Path to fastq files")
@click.option(
    "--config",
    default=pathlib.Path(__file__).parent.joinpath("config.conf"),
    help="Path to IRIDA config file",
)
@click.argument("path", default=os.getcwd())
def prepare(path, pattern, pid, name, pe, sort, config):
    """
    Prepare for uploading a folder of fastq files to IRIDA \n
    - Create project on IRIDA \n
    - Generate a sample list inside the folder \n
    """
    # :param sort: Sorting sample in numeric order
    # :param path: path to the folder of fastq files
    # :param pattern: pattern to scan, by default: *_R1_001.fastq.gz
    # :param pid: IRIDA project ID, you need to manually create in IRIDA control management
    # :param pe: Are the reads paired-end?
    # :return: A csv file SampleList.csv
    p = pathlib.Path(path)

    if pid is None:
        if name is None:
            run_date = re.search("[0-9]{6}(?=\_NB)", path)
            if run_date is not None:
                run_date = run_date.group()
            else:
                #     sys.exit("I could not find an expected folder name for IRIDA. Please name it manually")
                # if len(run_date) == 0:
                run_date = datetime.date.today().strftime("%y%m%d")
            project_name = f'QIB-{p.parts[-1].replace("_","-")}-{run_date}'
            logging.info(f"Project name is: {project_name}")
        else:
            project_name = name

        pid = create_project(name=project_name, config_file=config)
    if pe:
        regex = re.compile(
            "_S[0-9]{1,3}|_R[12].|_1.non_host.fastq.gz|_2.non_host.fastq.gz"
        )
    else:
        regex = re.compile(".fastq|.fq.")
    if not pe:
        pattern = "*.fastq.gz"

    fastqs = p.rglob(pattern)
    print(fastqs)
    fastq_names = [fq.name for fq in fastqs]
    _sorted_fastq_names = fastq_names
    # Sort sample
    if sort:
        _sorted_fastq_names = sorted(
            fastq_names, key=lambda s: int(regex.split(s)[0].split("_")[-1])
        )

    sample_ids = [regex.split(sp)[0] for sp in _sorted_fastq_names]
    sample_file = p.joinpath("SampleList.csv")
    # print(sorted(fastq_names, key=lambda s: int(regex.split(s)[0].split("_")[-1])))
    with sample_file.open(mode="w") as fh:
        fh.write("[Data]\n")
        fh.write("Sample_Name,Project_ID,File_Forward,File_Reverse\n")
        for i in range(0, len(_sorted_fastq_names)):
            if pe:
                if "_R1_" in _sorted_fastq_names[i]:
                    reverse_reads = _sorted_fastq_names[i].replace("_R1_", "_R2_")
                elif "_R1.non_host.fastq.gz" in _sorted_fastq_names[i]:
                    reverse_reads = _sorted_fastq_names[i].replace(
                        "_R1.non_host.fastq.gz", "_R2.non_host.fastq.gz"
                    )
                else:
                    raise ValueError(f"Invalid file name: {_sorted_fastq_names[i]}")
            else:
                reverse_reads = ""
            fh.write(
                f"{sample_ids[i]}, {pid}, {_sorted_fastq_names[i]}, {reverse_reads}\n"
            )
    print("Finish!")

def _upload(run_directory, force_upload, upload_mode, continue_upload):
    """
    Uploads a run directory to IRIDA.

    Args:
        run_directory (str): The path to the run directory.
        force_upload (bool): Whether to force the upload even if the run has already been uploaded.
        upload_mode (str): The upload mode to use.
        continue_upload (bool, optional): Whether to continue an interrupted upload. Defaults to False.

    Returns:
        int: The exit code of the upload process.
    """
    return core.upload.upload_run_single_entry(run_directory, force_upload, upload_mode, continue_upload).exit_code


def _upload_batch(batch_directory, force_upload, upload_mode, continue_upload):
    """
    Uploads a batch of folders to IRIDA.

    Args:
        batch_directory (str): The directory containing the batch of folders to upload.
        force_upload (bool): Flag indicating whether to force the upload, even if the files already exist in IRIDA.
        upload_mode (str): The upload mode to use. Possible values are 'create', 'update', or 'skip'.
        continue_upload (bool): Flag indicating whether to continue an interrupted upload.

    Returns:
        int: The exit code of the upload process.
    """
    return core.upload.batch_upload_single_entry(
        batch_directory, force_upload, upload_mode, continue_upload
    ).exit_code

@click.command()
@click.option('--force-upload', 'force_upload', is_flag=True, default=False, help="Force upload")
@click.option(
    "--continue-upload",
    "continue_upload",
    is_flag=True,
    default=False,
    help="Start uploading from where the last upload left off.",
)
@click.option(
    "--upload_mode",
    "upload_mode",
    type=click.Choice(["default", "assemblies", "fast5"]),
    default="default",
    help="Upload mode (default: default)",
)
@click.option('--config', default=pathlib.Path(__file__).parent.joinpath('config.conf'), help='Path to IRIDA config file')
@click.argument('directory', default=os.getcwd())
def upload(directory, force_upload, upload_mode, continue_upload, config):
    """
    Upload a run folder to IRIDA
    """
    sample_list = os.path.join(directory, 'SampleList.csv')
    assert os.path.exists(sample_list), f"ERROR! SampleList.csv not found in {directory}"
    assert os.access(
        sample_list, os.W_OK
    ), f"ERROR! Specified directory is not writable: {directory}"
    
    # if not os.access(directory, os.W_OK):  # Cannot access upload directory
    #     print("ERROR! Specified directory is not writable: {}".format(directory))
    #     sys.exit(1)
    
    logging.info(f'Current directory: {directory}')
    # Initialize API with flexible authentication and get the temporary config file path
    api, temp_config_path = initialize_irida_api(config)

    # Set up configuration using the temporary config file
    _config.set_config_file(temp_config_path)
    _config.setup()
    _upload(directory, force_upload, upload_mode, continue_upload)


@click.group()
def irida():
    pass

irida.add_command(prepare)
irida.add_command(upload)

if __name__ == '__main__':
    irida()
    # create_project()


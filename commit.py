import time
import yaml
import logging
import subprocess
from threading import Timer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff

log_file = './auto_commit.log'
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    filename=log_file,
                    filemode='a')
logger = logging.getLogger(__name__)

# Global timer
commit_timer = None


def execute_cmd_with_logging(cmd, message, cwd=None):
    """
    Execute a command and log the message.

    :param cmd: Command list
    :param message: Success message
    :param cwd: Current working directory
    """
    try:
        subprocess.run(cmd, check=True, cwd=cwd)
        logger.info(message)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command execution failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")


class Config:
    """
    Configuration class for loading configuration files.

    :param config_file: Path to the configuration file, default is 'config.yaml'
    """
    def __init__(self, config_file='config.yaml'):
        with open(config_file, 'r') as file:
            self.config = yaml.safe_load(file)

        self.watch_paths = self.config.get('watch_paths', [])
        self.repo_path = self.config.get('repo_path', '')
        self.commit_interval = self.config.get('commit_interval', 10)


class GitAutoCommitHandler(FileSystemEventHandler):
    """
    File system event handler class to handle file system change events.

    :param path: Path to watch
    :param config: Configuration object
    """
    def __init__(self, path, config):
        super().__init__()
        self.watch_path = path
        self.snapshot = DirectorySnapshot(self.watch_path)
        self.repo_path = config.repo_path
        self.commit_interval = config.commit_interval
        self.flag = 0

    def on_any_event(self, event):
        """
        Called when any file system event occurs.

        :param event: File system event
        """
        global commit_timer
        if commit_timer:
            commit_timer.cancel()

        # Set a timer to check the directory snapshot after a certain interval
        commit_timer = Timer(self.commit_interval, self.check_snapshot)
        commit_timer.start()

    def check_snapshot(self):
        """
        Check the directory snapshot for changes and perform synchronization and commit operations.
        """
        global commit_timer
        snapshot = DirectorySnapshot(self.watch_path)
        diff = DirectorySnapshotDiff(self.snapshot, snapshot)
        self.snapshot = snapshot
        commit_timer = None

        changes = {
            "files_created": diff.files_created,
            "files_deleted": diff.files_deleted,
            "files_modified": diff.files_modified,
            "files_moved": diff.files_moved,
            "dirs_created": diff.dirs_created,
            "dirs_deleted": diff.dirs_deleted,
            "dirs_modified": diff.dirs_modified,
            "dirs_moved": diff.dirs_moved
        }

        self.flag = 0
        for change_type, items in changes.items():
            if items:
                self.flag += 1
                logger.info(f"{change_type}: {items}")
        if self.flag:
            self.sync_and_commit()

    def sync_and_commit(self):
        """
        Synchronize the local directory to the repository and commit changes.
        """
        # Synchronize the local directory to the repository
        rsync_cmd = ['rsync', '-avz', '--delete', '--exclude-from=exclude_patterns', self.watch_path, self.repo_path]
        execute_cmd_with_logging(rsync_cmd, message="Directory synchronized successfully.")

        # Add all changes to git
        add_cmd = ['git', 'add', '-A']
        execute_cmd_with_logging(add_cmd, message="All files have been added.", cwd=self.repo_path)

        # Check git status
        status_cmd = ['git', 'status', '--porcelain']
        status_output = subprocess.check_output(status_cmd, cwd=self.repo_path).decode('utf-8').strip()

        if status_output:
            # Commit changes
            commit_cmd = ['git', 'commit', '-m', f'{self.flag} events committed']
            execute_cmd_with_logging(commit_cmd, message=f"{self.flag} events committed.",
                                     cwd=self.repo_path)
        else:
            logger.info("No changes to commit.")

        # Push to remote repository
        push_cmd = ['git', 'push']
        execute_cmd_with_logging(push_cmd, message="Pushed to remote repository successfully.", cwd=self.repo_path)


class AutoCommitManager:
    """
    Auto-commit manager class to start watchers.

    :param config: Configuration object
    """
    def __init__(self, config):
        self.config = config

    def start_watching(self):
        """
        Start watching specified paths for file system events.
        """
        event_handlers = []
        observers = []

        for path in self.config.watch_paths:
            event_handler = GitAutoCommitHandler(path, self.config)
            event_handlers.append(event_handler)

            observer = Observer()
            observer.schedule(event_handler, path=path, recursive=True)
            observer.start()
            observers.append(observer)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            for observer in observers:
                observer.stop()
        finally:
            for observer in observers:
                observer.join()


if __name__ == "__main__":
    conf = Config('./config.yaml')
    manager = AutoCommitManager(conf)
    manager.start_watching()


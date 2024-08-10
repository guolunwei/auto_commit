#!/bin/bash
set -e

if [ $UID -ne 0 ];then
    mkdir -p ~/.config/systemd/user
    cp auto-commit.service ~/.config/systemd/user
    systemctl --user daemon-reload
    systemctl --user enable auto-commit.service
    systemctl --user restart auto-commit.service
fi

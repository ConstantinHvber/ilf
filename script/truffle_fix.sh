#!/bin/bash

while true; do
  cur_pid=`pgrep -fla 'ganache' | cut -f1 -d' '`;
  elapsed_seconds=$(expr `ps -o etime= -p "${cur_pid}" | cut -f2 -d':'` + 0)

  if [[ ${elapsed_seconds} -ge 30 ]]; then
    echo "Killing ${cur_pid}";
    kill -9 ${cur_pid};
  fi

  sleep 5;
done



#!/bin/bash
#SBATCH --mem=300G
#SBATCH --requeue
#SBATCH --time=72:00:00
#SBATCH --cpus-per-task=9
#SBATCH --array=0-4

if [ $SLURM_ARRAY_TASK_ID -eq 0 ]; then
    SCHEME_NAME="SumPrefix"
elif [ $SLURM_ARRAY_TASK_ID -eq 1 ]; then
    SCHEME_NAME="MinimumLinearEMT"
elif [ $SLURM_ARRAY_TASK_ID -eq 2 ]; then
    SCHEME_NAME="MinimumSparseTable"
elif [ $SLURM_ARRAY_TASK_ID -eq 3 ]; then
    SCHEME_NAME="ModeASTable"
elif [ $SLURM_ARRAY_TASK_ID -eq 4 ]; then
    SCHEME_NAME="MedianAlphaApprox:0.5"
fi

python3 ../src/experiment.py \
    -s $SCHEME_NAME \
    -d ../data/*-gowalla.csv \
    -n localhost -p 8000 \
    -q all \
    -o gowalla-$SCHEME_NAME.csv \
    --debug \
    --num_processes 8

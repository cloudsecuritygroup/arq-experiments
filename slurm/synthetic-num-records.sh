#!/bin/bash
#SBATCH --mem=300G
#SBATCH --requeue
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=9
#SBATCH --array=0-6

if [ $SLURM_ARRAY_TASK_ID -eq 0 ]; then
    NUMBER_OF_RECORDS="10"
elif [ $SLURM_ARRAY_TASK_ID -eq 1 ]; then
    NUMBER_OF_RECORDS="100"
elif [ $SLURM_ARRAY_TASK_ID -eq 2 ]; then
    NUMBER_OF_RECORDS="1000"
elif [ $SLURM_ARRAY_TASK_ID -eq 3 ]; then
    NUMBER_OF_RECORDS="10000"
elif [ $SLURM_ARRAY_TASK_ID -eq 4 ]; then
    NUMBER_OF_RECORDS="100000"
elif [ $SLURM_ARRAY_TASK_ID -eq 5 ]; then
    NUMBER_OF_RECORDS="1000000"
elif [ $SLURM_ARRAY_TASK_ID -eq 6 ]; then
    NUMBER_OF_RECORDS="10000000"
fi

python3 ../src/experiment.py \
    -s MedianAlphaApprox:0.5 ModeASTable MinimumLinearEMT MinimumSparseTable \
    -n localhost -p 8000 -q all \
    -o synthetic-num-records-$NUMBER_OF_RECORDS.csv --debug \
    --num_processes 8 \
    --synthetic_domain_size "$NUMBER_OF_RECORDS" \
    --synthetic_sparsity_percent 100

#!/bin/bash
#SBATCH --mem=300G
#SBATCH --requeue
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=9
#SBATCH --array=0-8

if [ $SLURM_ARRAY_TASK_ID -eq 0 ]; then
    SPARSITY_PERCENT="10"
elif [ $SLURM_ARRAY_TASK_ID -eq 1 ]; then
    SPARSITY_PERCENT="20"
elif [ $SLURM_ARRAY_TASK_ID -eq 2 ]; then
    SPARSITY_PERCENT="30"
elif [ $SLURM_ARRAY_TASK_ID -eq 3 ]; then
    SPARSITY_PERCENT="40"
elif [ $SLURM_ARRAY_TASK_ID -eq 4 ]; then
    SPARSITY_PERCENT="50"
elif [ $SLURM_ARRAY_TASK_ID -eq 5 ]; then
    SPARSITY_PERCENT="60"
elif [ $SLURM_ARRAY_TASK_ID -eq 6 ]; then
    SPARSITY_PERCENT="70"
elif [ $SLURM_ARRAY_TASK_ID -eq 7 ]; then
    SPARSITY_PERCENT="80"
elif [ $SLURM_ARRAY_TASK_ID -eq 8 ]; then
    SPARSITY_PERCENT="90"
fi

python3 ../src/experiment.py \
    -s MedianAlphaApprox:0.5 ModeASTable MinimumLinearEMT MinimumSparseTable \
    -n localhost -p 8000 -q all \
    -o synthetic-density-$SPARSITY_PERCENT.csv --debug \
    --num_processes 8 \
    --synthetic_domain_size 100000 \
    --synthetic_sparsity_percent "$SPARSITY_PERCENT"

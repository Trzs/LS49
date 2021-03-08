#!/bin/bash -l

#SBATCH -q special    # regular or special queue
#SBATCH -N 1          # Number of nodes
#SBATCH -t 00:10:00   # wall clock time limit
#SBATCH -J test_gpu_job
#SBATCH -L SCRATCH    # job requires SCRATCH files
#SBATCH -C gpu
#SBATCH -A m1759      # allocation
#SBATCH -G 1          # devices per node
#SBATCH -c 10         # total threads requested per node
#SBATCH -o job%j.out
#SBATCH -e job%j.err
#SBATCH --exclusive

# -n, tasks to run; -N number of nodes; -c cpus per task;
# n = N x tasks_per_node (should be 40 tasks per node for Cori-gpu)

mkdir $SLURM_JOB_ID; cd $SLURM_JOB_ID
echo "jobstart $(date)";pwd;ls
srun -n 1 -c 2 libtbx.python $(libtbx.find_in_repositories LS49)/adse13_187/cyto_batch.py N_total=1 test_pixel_congruency=True mosaic_spread_samples=500 write_output=True write_experimental_data=True
echo "jobend $(date)";pwd;ls


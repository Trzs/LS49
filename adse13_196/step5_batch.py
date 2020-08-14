from __future__ import division, print_function
from six.moves import range
from scitbx.matrix import sqr
import libtbx.load_env # possibly implicit
from cctbx import crystal
from time import time
from omptbx import omp_get_num_procs
from scitbx.array_family import flex

# %%% boilerplate specialize to packaged big data %%%
import os
from LS49.adse13_196 import step5_pad
from LS49.sim import step4_pad
from LS49.spectra import generate_spectra
from LS49 import ls49_big_data
step5_pad.big_data = ls49_big_data
step4_pad.big_data = ls49_big_data
generate_spectra.big_data = ls49_big_data
from LS49.sim.util_fmodel import gen_fmodel
from LS49.adse13_196.step5_pad import data
# %%%%%%

# Develop procedure for MPI control

# first, sfall_channels DONE
# later, spectra to spectra iter
# data, why are we reading those files in all ranks?
# sfall_main not used?
# evaluate air + water as a singleton

def tst_one(image,spectra,crystal,random_orientation,sfall_channels):

  iterator = spectra.generate_recast_renormalized_image(image=image,energy=7120.,total_flux=1e12)

  quick = False
  if quick: prefix_root="step5_batch_%06d"
  else: prefix_root="step5_MPIbatch_%06d"

  file_prefix = prefix_root%image
  rand_ori = sqr(random_orientation)
  from LS49.adse13_196.step5_pad import run_sim2smv
  run_sim2smv(prefix = file_prefix,
              crystal = crystal,
              spectra=iterator,rotation=rand_ori,quick=quick,rank=rank,
              sfall_channels=sfall_channels)

if __name__=="__main__":
  log_by_rank = bool(int(os.environ.get("LOG_BY_RANK",0)))
  if log_by_rank:
    import io, sys
    import cProfile
    pr = cProfile.Profile()
    pr.enable()

  from libtbx.mpi4py import MPI
  comm = MPI.COMM_WORLD
  rank = comm.Get_rank()
  size = comm.Get_size()
  import omptbx
  workaround_nt = int(os.environ.get("OMP_NUM_THREADS",1))
  omptbx.omp_set_num_threads(workaround_nt)
  N_total = int(os.environ["N_SIM"]) # number of items to simulate
  N_stride = size # total number of worker tasks
  print("hello from rank %d of %d"%(rank,size),"with omp_threads=",omp_get_num_procs())
  import datetime
  start_elapse = time()
  if rank == 0:
    print("Rank 0 time", datetime.datetime.now())
    from LS49.spectra.generate_spectra import spectra_simulation
    from LS49.adse13_196.step5_pad import microcrystal
    print("hello2 from rank %d of %d"%(rank,size))
    SS = spectra_simulation()
    C = microcrystal(Deff_A = 4000, length_um = 4., beam_diameter_um = 1.0) # assume smaller than 10 um crystals
    from LS49 import legacy_random_orientations
    random_orientations = legacy_random_orientations(N_total)
    transmitted_info = dict(spectra = SS,
                            crystal = C,
                            random_orientations = random_orientations)
  else:
    transmitted_info = None
  transmitted_info = comm.bcast(transmitted_info, root = 0)
  comm.barrier()
  parcels = list(range(rank,N_total,N_stride))

  if log_by_rank:
    log_path = "rank_%d.log"%rank
    error_path = "rank_%d.err"%rank
    print("Rank %d redirecting stdout/stderr to"%rank, log_path, error_path)
    sys.stdout = io.TextIOWrapper(open(log_path,'ab', 0), write_through=True)
    sys.stderr = io.TextIOWrapper(open(error_path,'ab', 0), write_through=True)

  wavelength_A = 1.74 # general ballpark X-ray wavelength in Angstroms
  wavlen = flex.double([12398.425/(7070.5 + w) for w in range(100)])
  direct_algo_res_limit = 1.7

  local_data = data() # later put this through broadcast

  GF = gen_fmodel(resolution=direct_algo_res_limit,
                  pdb_text=local_data.get("pdb_lines"),algorithm="fft",wavelength=wavelength_A)
  GF.set_k_sol(0.435)
  GF.make_P1_primitive()

  # Generating sf for my wavelengths
  sfall_channels = {}
  for x in range(len(wavlen)):
    if rank > len(wavlen): break
    if x%size != rank: continue

    GF.reset_wavelength(wavlen[x])
    GF.reset_specific_at_wavelength(
                     label_has="FE1",tables=local_data.get("Fe_oxidized_model"),newvalue=wavlen[x])
    GF.reset_specific_at_wavelength(
                     label_has="FE2",tables=local_data.get("Fe_reduced_model"),newvalue=wavlen[x])
    sfall_channels[x]=GF.get_amplitudes()

  reports = comm.gather(sfall_channels, root = 0)
  if rank==0:
    sfall_channels = {}
    for report in reports:  sfall_channels.update(report)
  comm.barrier()

  if rank == 0:
    sfall_info = sfall_channels
  else:
    sfall_info = None
  sfall_channels = comm.bcast(sfall_info, root = 0)

  import random
  while len(parcels)>0:
    idx = random.choice(parcels)
    cache_time = time()
    print("idx------start-------->",idx,"rank",rank,time())
    # if rank==0: os.system("nvidia-smi")
    tst_one(image=idx,spectra=transmitted_info["spectra"],
        crystal=transmitted_info["crystal"],
        random_orientation=transmitted_info["random_orientations"][idx],
        sfall_channels=sfall_channels)
    parcels.remove(idx)
    print("idx------finis-------->",idx,"rank",rank,time(),"elapsed",time()-cache_time)
  print("OK exiting rank",rank,"at",datetime.datetime.now(),"seconds elapsed",time()-start_elapse)
  if log_by_rank:
    pr.disable()
    pr.dump_stats("cpu_%d.prof"%rank)

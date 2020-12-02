from __future__ import division, print_function
from time import time
start_elapse = time()

"""Modified version of the cyto_sim.py script with the following added features:
 - command line parameters following the PHIL + options convention
 - timing statements for weather2.py log scrapping
 - framework for MPI broadcast of big data if and when needed
 - runs on cctbx_project master branch (pickled spectra, for now)
 - Brewster style rank logger
 - Brewster style rank profiles
 - framework to use the exascale API if and when needed
"""

import libtbx.load_env # possibly implicit
from omptbx import omp_get_num_procs
from xfel.merging.application.utils.memory_usage import get_memory_usage
import os,sys

def parse_input():
  from iotbx.phil import parse
  master_phil="""
    N_total = 75
      .type = int
      .help = number of events to simulate
    log {
      outdir = .
        .type = path
        .help = Use "/mnt/bb/${USER}" for Summit NVME burst buffer
      by_rank = True
        .type = bool
        .help = Brewster-style split of logs for each rank
      rank_profile = False
        .type = bool
        .help = create a cProfile output for each rank
    }
    devices_per_node = 1
      .type = int
      .help = always 1 per Summit resource group, either 1 or 8 for Cori GPU
    use_exascale_api = True
      .type = bool
      .help = aim for 3 second image turnaround
  """
  phil_scope = parse(master_phil)
  # The script usage
  import libtbx.load_env # implicit import
  help_message = '''Jungfrau/cytochrome simuation.'''
  usage = ""
  '''Initialize the script.'''
  from dials.util.options import OptionParser
  # Create the parser
  parser = OptionParser(
        usage=usage,
        phil=phil_scope,
        epilog=help_message)

  # Parse the command line. quick_parse is required for MPI compatibility
  params, options = parser.parse_args(show_diff_phil=True,quick_parse=True)
  return params,options

def multipanel_sim(
  CRYSTAL, DETECTOR, BEAM, Famp, energies, fluxes,
  background_wavelengths, background_wavelength_weights,
  background_total_flux, background_sample_thick_mm,
  density_gcm3=1, molecular_weight=18,
  cuda=False, oversample=0, Ncells_abc=(50, 50, 50),
  mos_dom=1, mos_spread=0, beamsize_mm=0.001,
  show_params=False, crystal_size_mm=0.01, printout_pix=None, time_panels=True,
  verbose=0, default_F=0, interpolate=0, recenter=True, profile="gauss",
  spot_scale_override=None,
  add_water = False, add_air=False, water_path_mm=0.005, air_path_mm=0,
  adc_offset=0, readout_noise=3, psf_fwhm=0, gain=1, mosaicity_random_seeds=None):
  """
  :param CRYSTAL: dxtbx Crystal model
  :param DETECTOR: dxtbx detector model
  :param BEAM: dxtbx beam model
  :param Famp: gpu_channels_singleton(cctbx miller array (amplitudes))
  :param energies: list of energies to simulate the scattering
  :param fluxes:  list of pulse fluences per energy (same length as energies)
  :param cuda: whether to use GPU (only works for nvidia builds)
  :param oversample: pixel oversample factor (0 means nanoBragg will decide)
  :param Ncells_abc: number of unit cells along each crystal direction in the mosaic block
  :param mos_dom: number of mosaic domains in used to sample mosaic spread (texture)
  :param mos_spread: mosaicity in degrees (spherical cap width)
  :param beamsize_mm: focal size of the beam
  :param show_params: show the nanoBragg parameters
  :param crystal_size_mm: size of the crystal (increases the intensity of the spots)
  :param printout_pix: debug pixel position : tuple of (pixel_fast_coord, pixel_slow_coord)
  :param time_panels: show timing info
  :param verbose: verbosity level for nanoBragg (0-10), 0 is quiet
  :param default_F: default amplitude value for nanoBragg
  :param interpolate: whether to interpolate for small mosaic domains
  :param recenter: recenter for tilted cameras, deprecated
  :param profile: profile shape, can be : gauss, round, square, or tophat
  :param spot_scale_override: scale the simulated scattering bythis amounth (overrides value based on crystal thickness)
  :param add_water: add water to similated pattern
  :param add_air: add ait to simulated pattern
  :param water_path_mm: length of water the beam travels through
  :param air_path_mm: length of air the beam travels through
  :param adc_offset: add this value to each pixel in simulated pattern
  :param readout_noise: readout noise level (usually 3-5 ADU)
  :param psf_fwhm: point spread kernel FWHM
  :param gain: photon gain
  :param mosaicity_random_seeds: random seeds to simulating mosaic texture
  :return: list of [(panel_id0,simulated pattern0), (panel_id1, simulated_pattern1), ...]
  """
  from simtbx.nanoBragg.nanoBragg_beam import NBbeam
  from simtbx.nanoBragg.nanoBragg_crystal import NBcrystal
  from simtbx.nanoBragg.sim_data import SimData
  from simtbx.nanoBragg.utils import get_xray_beams
  from scitbx.array_family import flex
  from scipy import constants
  import numpy as np
  ENERGY_CONV = 10000000000.0 * constants.c * constants.h / constants.electron_volt

  nbBeam = NBbeam()
  nbBeam.size_mm = beamsize_mm
  nbBeam.unit_s0 = BEAM.get_unit_s0()
  wavelengths = ENERGY_CONV / np.array(energies)
  nbBeam.spectrum = list(zip(wavelengths, fluxes))

  nbCrystal = NBcrystal()
  nbCrystal.dxtbx_crystal = CRYSTAL
  #nbCrystal.miller_array = None # use the gpu_channels_singleton mechanism instead
  nbCrystal.Ncells_abc = Ncells_abc
  nbCrystal.symbol = CRYSTAL.get_space_group().info().type().lookup_symbol()
  nbCrystal.thick_mm = crystal_size_mm
  nbCrystal.xtal_shape = profile
  nbCrystal.n_mos_domains = mos_dom
  nbCrystal.mos_spread_deg = mos_spread

  pid = 0 # remove the loop, use C++ iteration over detector panels
  use_exascale_api = True
  if use_exascale_api:
    tinit = time()
    S = SimData()
    S.detector = DETECTOR
    S.beam = nbBeam
    S.crystal = nbCrystal
    S.panel_id = pid
    S.using_cuda = cuda
    S.using_omp = False
    S.add_air = add_air
    S.air_path_mm = air_path_mm
    S.add_water = add_water
    S.water_path_mm = water_path_mm
    S.readout_noise = readout_noise
    S.gain = gain
    S.psf_fwhm = psf_fwhm
    S.include_noise = False

    if mosaicity_random_seeds is not None:
      S.mosaic_seeds = mosaicity_random_seeds

    S.instantiate_nanoBragg(verbose=verbose, oversample=oversample, interpolate=interpolate,
      device_Id=Famp.get_deviceID(),default_F=default_F, adc_offset=adc_offset)

    SIM = S.D # the nanoBragg instance
    assert Famp.get_deviceID()==SIM.device_Id
    assert Famp.get_nchannels() == 1 # non-anomalous scenario

    from simtbx.gpu import exascale_api
    gpu_simulation = exascale_api(nanoBragg = SIM)
    gpu_simulation.allocate_cuda() # presumably done once for each image

    from simtbx.gpu import gpu_detector as gpud
    gpu_detector = gpud(deviceId=SIM.device_Id, detector=DETECTOR,
                        beam=BEAM)
    gpu_detector.each_image_allocate_cuda()

    # revisit the allocate cuda for overlap with detector, sync up please
    x = 0 # only one energy channel
    #SIM.flux = background_total_flux
      #SIM.flux = self.flux[x]
      #SIM.wavelength_A = self.wavlen[x]
    from libtbx.development.timers import Profiler
    P = Profiler("from gpu amplitudes cuda")
    gpu_simulation.add_energy_channel_from_gpu_amplitudes_cuda(
      x, Famp, gpu_detector)
    del P
#now in position to implement the detector panel loop
# figure out whether flux and wavelength_A are used
# figure out if Derek's panel recentering is relevant

    per_image_scale_factor = 1./len(energies)
    gpu_detector.scale_in_place_cuda(per_image_scale_factor) # apply scale directly on GPU

    cuda_background = True
    if cuda_background:
      SIM.beamsize_mm = beamsize_mm

      wavelength_weights = np.array(background_wavelength_weights)
      weights = wavelength_weights / wavelength_weights.sum() * background_total_flux
      spectrum = list(zip(background_wavelengths, weights))
      xray_beams = get_xray_beams(spectrum, BEAM)
      SIM.xray_beams = xray_beams
 #XXX assert these are the same:
      from simtbx.nanoBragg.tst_gauss_argchk import water
      SIM.Fbg_vs_stol = water
      SIM.Fbg_vs_stol = flex.vec2_double([
      (0, 2.57), (0.0365, 2.58), (0.07, 2.8), (0.12, 5), (0.162, 8), (0.18, 7.32), (0.2, 6.75),
      (0.216, 6.75), (0.236, 6.5), (0.28, 4.5), (0.3, 4.3), (0.345, 4.36), (0.436, 3.77), (0.5, 3.17)])
      SIM.flux=sum(weights)
      SIM.amorphous_sample_thick_mm = background_sample_thick_mm
      SIM.amorphous_density_gcm3 = density_gcm3
      SIM.amorphous_molecular_weight_Da = molecular_weight

      gpu_simulation.add_background_cuda(gpu_detector)
    packed_numpy = gpu_detector.get_raw_pixels_cuda().as_numpy_array()
    gpu_detector.each_image_free_cuda()
    print("done free")

    return packed_numpy

def tst_one(i_exp,spectra,Fmerge,gpu_channels_singleton,rank,params):
    from simtbx.nanoBragg import utils
    from dxtbx.model.experiment_list import ExperimentListFactory
    import numpy as np

    print("Experiment %d" % i_exp, flush=True)
    sys.stdout.flush()

    save_data_too = True
    outfile = "boop_%d.hdf5" % i_exp
    experiment_file = "/global/cfs/cdirs/m3562/der/run795/top_%d.expt" % i_exp
    refl_file = "/global/cfs/cdirs/m3562/der/run795/top_%d.refl" % i_exp
    cuda = True  # False  # whether to use cuda
    omp = False
    ngpu_on_node = 1 # 8  # number of available GPUs
    mosaic_spread = 0.07  # degrees
    mosaic_spread_samples = 500 # 30  # 50  # number of mosaic blocks sampling mosaicity
    Ncells_abc = 30, 30, 10  # medians from best stage1
    ev_res = 1.5  # resolution of the downsample spectrum
    total_flux = 1e12  # total flux across channels
    beamsize_mm = 0.000886226925452758  # sqrt of beam focal area
    spot_scale = 500. # 5.16324  # median from best stage1
    plot_spec = False  # plot the downsample spectra before simulating
    oversample = 1  # oversample factor, 1,2, or 3 probable enough
    panel_list = None  # integer list of panels, usefule for debugging
    rois_only = False  # only set True if you are running openMP, or CPU-only (i.e. not for GPU)
    include_background = True  # default is to add water background 100 mm thick
    verbose = 0  # leave as 0, unles debug
    flat = True  # enfore that the camera has 0 thickness
    # <><><><><><><><><><><><><><><><>

    # XXX new code
    El = ExperimentListFactory.from_json_file(experiment_file,
                                              check_format=True)
    exper = El[0]


    crystal = exper.crystal
    detector = exper.detector
    if flat:
        from dxtbx_model_ext import SimplePxMmStrategy
        for panel in detector:
            panel.set_px_mm_strategy(SimplePxMmStrategy())
            panel.set_mu(0)
            panel.set_thickness(0)

    beam = exper.beam

    # XXX new code
    spec = exper.imageset.get_spectrum(0)
    energies_raw, weights_raw = spec.get_energies_eV().as_numpy_array(), \
                                spec.get_weights().as_numpy_array()
    energies, weights = utils.downsample_spectrum(energies_raw, weights_raw, method=1, total_flux=total_flux,
                                                  ev_width=ev_res)

    if flat:
        assert detector[0].get_thickness() == 0

    if panel_list is None:
        panel_list = list(range(len(detector)))

    pids_for_rank = panel_list
    device_Id = 0
    if gpu_channels_singleton is not None:
      device_Id = gpu_channels_singleton.get_deviceID()

    print("Rank %d will use device %d" % (rank, device_Id))
    show_params = (rank == 0)  # False
    time_panels = (rank == 0)

    mn_energy = (energies*weights).sum() / weights.sum()
    mn_wave = utils.ENERGY_CONV / mn_energy

    if params.use_exascale_api:
      BEG=time()
      print (gpu_channels_singleton.get_deviceID(),"device")
      Famp_is_uninitialized = ( gpu_channels_singleton.get_nchannels() == 0 ) # uninitialized
      if Famp_is_uninitialized:
        F_P1 = Fmerge.expand_to_p1()
        for x in range(1):  # in this scenario, amplitudes are independent of lambda
          gpu_channels_singleton.structure_factors_to_GPU_direct_cuda(
          x, F_P1.indices(), F_P1.data())
      assert gpu_channels_singleton.get_nchannels() == 1

      JF16M_numpy_array = multipanel_sim(
        CRYSTAL=crystal, DETECTOR=detector, BEAM=beam,
        Famp = gpu_channels_singleton,
        energies=list(energies), fluxes=list(weights),
        background_wavelengths=[mn_wave], background_wavelength_weights=[1],
        background_total_flux=total_flux,background_sample_thick_mm=0.5,
        cuda=True,
        oversample=oversample, Ncells_abc=Ncells_abc,
        mos_dom=mosaic_spread_samples, mos_spread=mosaic_spread,
        beamsize_mm=beamsize_mm,show_params=show_params,
        time_panels=time_panels, verbose=verbose,
        spot_scale_override=spot_scale)
      print ("Exascale time",time()-BEG)
      if save_data_too:
        data = exper.imageset.get_raw_data(0)

      tsave = time()
      img_sh = JF16M_numpy_array.shape
      assert img_sh == (256,254,254)
      num_output_images = 1 + int(save_data_too)
      print("Saving exascale output data of shape", img_sh)
      beam_dict = beam.to_dict()
      det_dict = detector.to_dict()
      try:
        beam_dict.pop("spectrum_energies")
        beam_dict.pop("spectrum_weights")
      except Exception: pass
# XXX no longer have two separate files
      with utils.H5AttributeGeomWriter("exap_%d.hdf5"%i_exp,
                                image_shape=img_sh, num_images=num_output_images,
                                detector=det_dict, beam=beam_dict,
                                detector_and_beam_are_dicts=True) as writer:
        writer.add_image(JF16M_numpy_array)

        if save_data_too:
            data = [data[pid].as_numpy_array() for pid in panel_list]
            writer.add_image(data)

      tsave = time() - tsave
      print("Saved output to file %s. Saving took %.4f sec" % ("exap_%d.hdf5"%i_exp, tsave, ))

    #optional background
    backgrounds = {pid: None for pid in panel_list}
    if include_background:
        backgrounds = {pid: utils.sim_background( # default is for water
                detector, beam, wavelengths=[mn_wave], wavelength_weights=[1],
                total_flux=total_flux,
                pidx=pid, beam_size_mm=beamsize_mm, sample_thick_mm=0.5) # 0.1)
            for pid in pids_for_rank}

    pid_and_pdata = utils.flexBeam_sim_colors(
      CRYSTAL=crystal, DETECTOR=detector, BEAM=beam,
      energies=list(energies), fluxes=list(weights), Famp=Fmerge,
      pids=pids_for_rank, cuda=cuda, device_Id=device_Id,
      oversample=oversample, Ncells_abc=Ncells_abc, verbose=verbose,
      time_panels=time_panels, show_params=show_params, spot_scale_override=spot_scale,
      mos_dom=mosaic_spread_samples, mos_spread=mosaic_spread, beamsize_mm=beamsize_mm,
      background_raw_pixels=backgrounds, include_noise=False, rois_perpanel=None)

    pid_and_pdata = sorted(pid_and_pdata, key=lambda x: x[0])
    _, pdata = zip(*pid_and_pdata)

    # pdata is a list of 256 2D numpy arrays, now.

    if len(panel_list) != len(detector):
        print("Cant save partial detector image, exiting..")
        exit()
        #from dxtbx.model import Detector
        #new_det = Detector()
        #for pid in panel_list:
        #    new_det.add_panel(detector[pid])
        #detector = new_det
    if save_data_too:
        data = exper.imageset.get_raw_data(0)

    tsave = time()
    pdata = np.array(pdata) # now pdata is a numpy array of shape 256,254,254
    img_sh = pdata.shape
    num_output_images = 3 + int(save_data_too) #NKS FIXME
    print("Saving output data of shape", img_sh)
    print("BOOPZ: Rank=%d ; i_exp=%d, RAM usage=%f" % (rank, i_exp,get_memory_usage()/1e6 ))
    beam_dict = beam.to_dict()
    det_dict = detector.to_dict()
    try:
      beam_dict.pop("spectrum_energies")
      beam_dict.pop("spectrum_weights")
    except Exception: pass
    with utils.H5AttributeGeomWriter(outfile, image_shape=img_sh, num_images=num_output_images,
                                detector=det_dict, beam=beam_dict,
                                detector_and_beam_are_dicts=True) as writer:
        writer.add_image(JF16M_numpy_array/pdata)
        writer.add_image(JF16M_numpy_array)
        writer.add_image(pdata)

        if save_data_too:
            data = [data[pid].as_numpy_array() for pid in panel_list]
            writer.add_image(data)

    tsave = time() - tsave
    print("Saved output to file %s. Saving took %.4f sec" % (outfile, tsave, ))


def run_batch_job(test_without_mpi=False):
  params,options = parse_input()
  if params.log.by_rank:
    import io, sys
  if params.log.rank_profile:
    import cProfile
    pr = cProfile.Profile()
    pr.enable()

  if test_without_mpi:
    from LS49.adse13_196.mock_mpi import mpiEmulator
    MPI = mpiEmulator()
  else:
    from libtbx.mpi4py import MPI

  comm = MPI.COMM_WORLD
  rank = comm.Get_rank()
  size = comm.Get_size()
  import omptbx
  workaround_nt = int(os.environ.get("OMP_NUM_THREADS",1))
  omptbx.omp_set_num_threads(workaround_nt)
  N_stride = size # total number of worker tasks
  print("hello from rank %d of %d"%(rank,size),"with omp_threads=",omp_get_num_procs())
  import datetime
  start_comp = time()

  print(rank, time(),
    "finished with the calculation of channels, now construct single broadcast")

  if rank == 0:
    print("Rank 0 time", datetime.datetime.now())

    spectrum_dict = {}
    #with open("../test.pickle","rb") as F:
    #  for i_exp in range(75):
    #    import pickle
    #    i_exp_p, energies, weights = pickle.load(F)
    #    assert i_exp == i_exp_p
    #    spectrum_dict[i_exp] = (energies, weights)

    from iotbx.reflection_file_reader import any_reflection_file
    merge_file = "/global/cfs/cdirs/m3562/der/cyto_init_merge.mtz"
    Fmerge = any_reflection_file(merge_file).as_miller_arrays()[0].as_amplitude_array()

    if comm.rank == 0:
        print("Fmerge min/max = %f / %f" % (min(Fmerge.data()), max(Fmerge.data())))

    transmitted_info = dict(spectra = spectrum_dict,
                            amplitudes = Fmerge,
                            )
  else:
    transmitted_info = None
  transmitted_info = comm.bcast(transmitted_info, root = 0)
  comm.barrier()
  parcels = list(range(rank,params.N_total,N_stride))

  print(rank, time(), "finished with single broadcast, now set up the rank logger")

  if params.log.by_rank:
    expand_dir = os.path.expandvars(params.log.outdir)
    log_path = os.path.join(expand_dir,"rank_%d.log"%rank)
    error_path = os.path.join(expand_dir,"rank_%d.err"%rank)
    #print("Rank %d redirecting stdout/stderr to"%rank, log_path, error_path)
    sys.stdout = io.TextIOWrapper(open(log_path,'ab', 0), write_through=True)
    sys.stderr = io.TextIOWrapper(open(error_path,'ab', 0), write_through=True)

  print(rank, time(), "finished with the rank logger, now construct the GPU cache container")

  try:
    from simtbx.gpu import gpu_energy_channels
    gpu_channels_singleton = gpu_energy_channels (
      deviceId = rank % params.devices_per_node )
      # singleton will instantiate, regardless of cuda, device count, or exascale API
  except ImportError:
    gpu_channels_singleton = None
  comm.barrier()
  import random
  while len(parcels)>0:
    idx = random.choice(parcels)
    cache_time = time()
    print("idx------start-------->",idx,"rank",rank,time())
    # if rank==0: os.system("nvidia-smi")
    tst_one(i_exp=idx,spectra=transmitted_info["spectra"],
        Fmerge=transmitted_info["amplitudes"],
        gpu_channels_singleton=gpu_channels_singleton,
        rank=rank,params=params
    )
    parcels.remove(idx)
    print("idx------finis-------->",idx,"rank",rank,time(),"elapsed",time()-cache_time)
  comm.barrier()
  print("Overall rank",rank,"at",datetime.datetime.now(),
        "seconds elapsed after srun startup %.3f"%(time()-start_elapse))
  print("Overall rank",rank,"at",datetime.datetime.now(),
        "seconds elapsed after Python imports %.3f"%(time()-start_comp))
  if params.log.rank_profile:
    pr.disable()
    pr.dump_stats("cpu_%d.prof"%rank)

if __name__=="__main__":
  run_batch_job()

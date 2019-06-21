from __future__ import print_function, division
from six.moves import range
from scitbx.array_family import flex
from LS49.sim.util_fmodel import gen_fmodel
from LS49.sim.step5_pad import data
from cctbx import crystal_orientation
from scitbx.matrix import sqr
from simtbx.nanoBragg import shapetype
from simtbx.nanoBragg import nanoBragg
from six.moves import StringIO
import scitbx
import math
from scitbx.matrix import col
from LS49.work2_for_aca_lsq.util_partiality import channel_pixels
import os
json_glob = os.environ["JSON_GLOB"]
pickle_glob = os.environ["PICKLE_GLOB"]

def ersatz_all_orientations(N_total=100000):
    ori_N_total = N_total # number of items to simulate
    mt = flex.mersenne_twister(seed=0)
    random_orientations = []
    for iteration in range(ori_N_total):
      random_orientations.append( mt.random_double_r3_rotation_matrix() )
    return random_orientations

class differential_roi_manager(object):
  def __init__(self,key,spotlist,spectrum,crystal):

    from dxtbx.model.experiment_list import ExperimentListFactory
    from six.moves import cPickle as pickle
    E = ExperimentListFactory.from_json_file(json_glob%key,check_format=False)[0] # the dials experiment
    C = E.crystal
    C.show()
    self.data = pickle.load(open(pickle_glob%key,"rb")) # the dials reflections file
    self.gen_fmodel_adapt() # generate Fmodel to obtain CB_OP_C_P
    self.models4 = self.get_idx_rotation_models(key) # alignment between dials refine and coarse ground truth
    self.perform_simulations(spectrum,crystal)
    self.model_rotations_and_spots(key,spotlist) # get shoeboxes and differential rotations
    #self.perform_one_simulation()

  def __del__(self):
    self.SIM.free_all()

  def perform_simulations(self,spectrum, crystal, tophat_spectrum=True):
    #borrow code from util_partiality.
    #def run_sim2smv(ROI,prefix,crystal,spectra,rotation,rank,tophat_spectrum=True,quick=False):

    direct_algo_res_limit = 1.7

    self.wavlen, self.flux, self.wavelength_A = next(spectrum) # list of lambdas, list of fluxes, average wavelength

    if tophat_spectrum:
      sum_flux = flex.sum(self.flux)
      ave_flux = sum_flux/60. # 60 energy channels
      for ix in range(len(self.wavlen)):
        energy = 12398.425 / self.wavlen[ix]
        if energy>=7090 and energy <=7150:
          self.flux[ix]=ave_flux
        else:
          self.flux[ix]=0.

    # use crystal structure to initialize Fhkl array
    self.sfall_main.show_summary(prefix = "Amplitudes used ")
    N = crystal.number_of_cells(self.sfall_main.unit_cell())
    self.crystal = crystal # delete later
    self.N = N # delete later
    SIM = nanoBragg(detpixels_slowfast=(3000,3000),pixel_size_mm=0.11,Ncells_abc=(N,N,N),
      # workaround for problem with wavelength array, specify it separately in constructor.
      wavelength_A=self.wavelength_A,verbose=0)
    self.SIM = SIM
    SIM.adc_offset_adu = 10 # Do not offset by 40
    SIM.mosaic_spread_deg = 0.05 # interpreted by UMAT_nm as a half-width stddev
    SIM.mosaic_domains = 50  # mosaic_domains setter must come after mosaic_spread_deg setter
    SIM.distance_mm=141.7

    UMAT_nm = flex.mat3_double()
    mersenne_twister = flex.mersenne_twister(seed=0)
    scitbx.random.set_random_seed(1234)
    rand_norm = scitbx.random.normal_distribution(mean=0, sigma=SIM.mosaic_spread_deg * math.pi/180.)
    g = scitbx.random.variate(rand_norm)
    mosaic_rotation = g(SIM.mosaic_domains)
    for m in mosaic_rotation:
      site = col(mersenne_twister.random_double_point_on_sphere())
      UMAT_nm.append( site.axis_and_angle_as_r3_rotation_matrix(m,deg=False) )
    SIM.set_mosaic_blocks(UMAT_nm)
    self.UMAT_nm = UMAT_nm # delete later

    # get same noise each time this test is run
    SIM.seed = 1
    SIM.oversample=1
    SIM.wavelength_A = self.wavelength_A
    SIM.polarization=1
    # this will become F000, marking the beam center
    SIM.default_F=0
    SIM.Fhkl=self.sfall_main

    SIM.xtal_shape=shapetype.Gauss # both crystal & RLP are Gaussian
    SIM.progress_meter=False
    SIM.show_params()
    # flux is always in photons/s
    SIM.flux=1e12
    SIM.exposure_s=1.0 # so total fluence is e12
    # assumes round beam
    SIM.beamsize_mm=0.003 #cannot make this 3 microns; spots are too intense
    temp=SIM.Ncells_abc
    print("Ncells_abc=",SIM.Ncells_abc)
    SIM.Ncells_abc=temp

  def perform_one_simulation(self):
    ROI = self.ROI
    Amatrix_rot = self.models4["Amat"]
    self.SIM.Amatrix_RUB = Amatrix_rot
    #workaround for failing init_cell, use custom written Amatrix setter
    Amatrecover = sqr(self.SIM.Amatrix).transpose() # recovered Amatrix from SIM
    Ori = crystal_orientation.crystal_orientation(Amatrecover, crystal_orientation.basis_type.reciprocal)
    print("Python unit cell from SIM state",Ori.unit_cell())

    self.SIM.seed = 1
    # simulated crystal is only 125 unit cells (25 nm wide)
    # amplify spot signal to simulate physical crystal of 4000x larger: 100 um (64e9 x the volume)
    output = StringIO() # open("myfile","w")
    #  make_response_plot = response_plot(False,title=prefix)

    for x in range(0,100,2): #len(flux)):
      if self.flux[x]==0.0:continue
      print("+++++++++++++++++++++++++++++++++++++++ Wavelength",x)
      CH = channel_pixels(ROI,self.wavlen[x],self.flux[x],self.N,self.UMAT_nm,Amatrix_rot,self.GF,output)
      incremental_signal = CH.raw_pixels * self.crystal.domains_per_crystal
      #  make_response_plot.append_channel(x,ROI,incremental_signal)
      # if x in [26,40,54,68]: # subsample 7096, 7110, 7124, 7138 eV
      #   print ("----------------------> subsample", x)
      #   make_response_plot.incr_subsample(x,ROI,incremental_signal)
      #make_response_plot.increment(x,ROI,incremental_signal)
      self.SIM.raw_pixels += incremental_signal;
      CH.free_all()

    #message = output.getvalue().split()
    #miller = (int(message[4]),int(message[5]),int(message[6]))
    #intensity = float(message[9]);

    pixels = self.SIM.raw_pixels
    roi_pixels = pixels[ROI[1][0]:ROI[1][1], ROI[0][0]:ROI[0][1]]
    print("Reducing full shape of",pixels.focus(),"to ROI of",roi_pixels.focus())
    #  make_response_plot.plot(roi_pixels,miller)
    #  return dict(roi_pixels=roi_pixels,miller=miller,intensity=intensity,
             # channels=make_response_plot.channels)

  def model_rotations_and_spots(self,key,spotlist):
    M = self.data["miller_index"]
    for model in self.models4:
      for spot in spotlist:
        ('a', 'asu_idx_C2_setting', 'bkgrd_a', 'channels', 'compute_functional_and_gradients', 'image_no', 'n', 'orig_idx_C2_setting',
         'print_step', 'roi', 'sb_data', 'simtbx_P1_miller', 'simtbx_intensity_7122', 'x')
        S = (spot.orig_idx_C2_setting)
        idx = M.first_index(S)
        shoe = self.data["shoebox"][idx]
        B = shoe.bbox
        self.ROI = ((B[0],B[1]),(B[2],B[3]))
        print ("C2",S,self.ROI)

        from LS49.ML_push.shoebox_troubleshoot import pprint3,pprint
        pprint3 (shoe.data)
        pprint (spot.sb_data)
        pprint (spot.roi)


      #for roi in group of spots:
      #  perform util_partiality run_sim2smv
      #  display results

  def gen_fmodel_adapt(self):
    direct_algo_res_limit = 1.7
    self.GF = gen_fmodel(resolution=direct_algo_res_limit,pdb_text=data(
         ).get("pdb_lines"),algorithm="fft",wavelength=7122)
    self.CB_OP_C_P = self.GF.xray_structure.change_of_basis_op_to_primitive_setting() # from C to P, for ersatz model
    self.GF.set_k_sol(0.435)
    self.GF.make_P1_primitive()
    self.sfall_main = self.GF.get_amplitudes()

  def get_idx_rotation_models(self,idx):
    rotation = sqr(ersatz_all_orientations()[idx])
    Amat = (rotation * sqr(self.sfall_main.unit_cell().orthogonalization_matrix())).transpose()
    from LS49.work_pre_experiment.post5_ang_misset import get_item
    from LS49.ML_push.exploratory_missetting import metric
    R = get_item(idx)
    print ("coarse ground truth with index",idx)
    C = crystal_orientation.crystal_orientation(
      Amat,crystal_orientation.basis_type.direct)
    C.show(legend="ground truth, P1")
    C2 = C.change_basis(self.CB_OP_C_P.inverse())
    C2.show(legend="ground truth, C2")
    direct_A = R["integrated_crystal_model"].get_A_inverse_as_sqr() # from dials model, integration step
    permute = sqr((0,0,1,0,1,0,-1,0,0))
    sim_compatible = direct_A*permute # permute columns when post multiplying
    P = crystal_orientation.crystal_orientation(
      sim_compatible,crystal_orientation.basis_type.direct)
    P.show(legend="dials_integrated, C2")
    PR = P.change_basis(self.CB_OP_C_P)
    PR.show(legend="dials_integrated, primitive setting")
    PRC2 = PR.change_basis(self.CB_OP_C_P.inverse()) # dials integrated, C2
    cb_op_align = PR.best_similarity_transformation(C,200,1)
    align_PR = PR.change_basis(sqr(cb_op_align))
    align_PR.show(legend="dials_integrated, P1, aligned")
    print("alignment matrix", cb_op_align)
    metric_val = metric(align_PR,C)
    print("Key %d aligned angular offset is %12.9f deg."%(idx, metric_val))
    print("Key %d alignC2 angular offset is %12.9f deg."%(idx, metric(align_PR.change_basis(self.CB_OP_C_P.inverse()),C2)))
    # coarse, dials crystal orientation models = C, align_PR
    # apply Rotx:
    import math
    align_PR_dx = align_PR.rotate_thru((1.0,0.0,0.0), math.pi* 0.01/180.)
    align_PR_dy = align_PR.rotate_thru((0.0,1.0,0.0), math.pi* 0.01/180.)
    align_PR_dz = align_PR.rotate_thru((0.0,0.0,1.0), math.pi* 0.01/180.)
    return (dict(Amat=align_PR.direct_matrix(),Amat_dx=align_PR_dx.direct_matrix(),
            Amat_dy=align_PR_dy.direct_matrix(), Amat_dz=align_PR_dz.direct_matrix()))

"""
work out the basic code for
OK 1) getting CB_OP
OK 2) Getting sfall_main
OK 3) getting the coarse ground truth
OK 4) getting the dials refine
OK 5) applying rotational perturbations to dials refine
6) performing 7150 eV simulations for all three orientations (GT, RXGT, RYGT)
"""

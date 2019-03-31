from __future__ import division, print_function
from six.moves import cPickle, range
from scitbx.array_family import flex
import scitbx
import os
import math
from scitbx.matrix import col

ls49_big_data = os.environ["LS49_BIG_DATA"] # get absolute path from environment
filename = "mosaic_domains.pickle"

def channel_wavelength_fmodel(create):
  N_mosaic_domains = 25
  mosaic_spread_deg = 0.05 # interpreted by UMAT_nm as a half-width stddev

  UMAT_nm = flex.mat3_double()
  mersenne_twister = flex.mersenne_twister(seed=0)
  scitbx.random.set_random_seed(1234)
  rand_norm = scitbx.random.normal_distribution(mean=0, sigma=mosaic_spread_deg * math.pi/180.)
  g = scitbx.random.variate(rand_norm)
  mosaic_rotation = g(N_mosaic_domains)
  for m in mosaic_rotation:
    site = col(mersenne_twister.random_double_point_on_sphere())
    UMAT_nm.append( site.axis_and_angle_as_r3_rotation_matrix(m,deg=False) )

  if create: # write the reference for the first time
      cPickle.dump(UMAT_nm,
      open(os.path.join(ls49_big_data,"reference",filename),"wb"),cPickle.HIGHEST_PROTOCOL)
  else: # read the reference and assert sameness to production run
      UMAT_ref = cPickle.load(open(os.path.join(ls49_big_data,"reference",filename),"rb"))
      for x in range(len(UMAT_nm)):
        print(x," ".join(
          ["%18.15f"%UMAT_ref[x][z] for z in range(9)]
        ))
        assert UMAT_nm[x] == UMAT_ref[x]
  expected_output =  """
0  0.999998267296033  0.000314549772964 -0.001834792460335 -0.000313914658246  0.999999890722460  0.000346428427106  0.001834901228816 -0.000345851858600  0.999998256760467
1  0.999999401374518 -0.001093965354793 -0.000022145152202  0.001093965187403  0.999999401591257 -0.000007569488342  0.000022153419708  0.000007545257785  0.999999999726148
2  0.999999801467673 -0.000552262055032 -0.000303432425910  0.000552402412062  0.999999740391472  0.000462675441762  0.000303176829046 -0.000462842966710  0.999999846930087
3  0.999999983131323 -0.000128345771627 -0.000131395269042  0.000128333948366  0.999999987716380 -0.000089986875444  0.000131406816863  0.000089970011452  0.999999987318823
4  0.999999939177732  0.000229633268022 -0.000262513038581 -0.000229356082241  0.999999416724826  0.001055436305975  0.000262755248752 -0.001055376032819  0.999999408570379
5  0.999999910424119  0.000074346969879 -0.000416682470429 -0.000074272117669  0.999999981104570  0.000179651085100  0.000416695819069 -0.000179620121118  0.999999897050598
6  0.999999839169819 -0.000412121153514  0.000389636357650  0.000411963202324  0.999999832978935  0.000405374420381 -0.000389803355946 -0.000405213839343  0.999999841927531
7  0.999999842406599  0.000537283555802 -0.000162828617419 -0.000537269077077  0.999999851714843  0.000088950721240  0.000162876385033 -0.000088863224441  0.999999982787305
8  0.999999998014802 -0.000026575343477  0.000057132714621  0.000026583789690  0.999999988718424 -0.000147839285436 -0.000057128785097  0.000147840803947  0.999999987439699
9  0.999998057633921 -0.001453745072041 -0.001330922105732  0.001454343778621  0.999998841647111  0.000448986202580  0.001330267852576 -0.000450920948768  0.999999013528383
10  0.999999997971440  0.000061598391708  0.000016209788496 -0.000061599691417  0.999999994887343  0.000080192222104 -0.000016204848701 -0.000080193220459  0.999999996653225
11  0.999999265662547 -0.000478626669693  0.001113369156055  0.000479096566435  0.999999796266762 -0.000421820950198 -0.001113167034468  0.000422354051779  0.999999291237853
12  0.999999538244861 -0.000846540575552 -0.000454839662641  0.000846274936930  0.999999471438253 -0.000583902343308  0.000455333719256  0.000583517154281  0.999999726089430
13  0.999999949261451  0.000314395234259  0.000051310161279 -0.000314384708429  0.999999929564413 -0.000205020547032 -0.000051374615148  0.000205004405499  0.999999977666921
14  0.999999954920238 -0.000235846550558  0.000185838441385  0.000235810614340  0.999999953500384  0.000193371623093 -0.000185884038773 -0.000193327791699  0.999999964035744
15  0.999999917252159  0.000383638850461  0.000135339971624 -0.000383672701080  0.999999895103052  0.000250178222193 -0.000135243979342 -0.000250230127743  0.999999959546974
16  0.999999963224907  0.000270093093040  0.000024492984589 -0.000270090252349  0.999999956808176 -0.000115909024523 -0.000024524289758  0.000115902404944  0.999999992982596
17  0.999999962031797  0.000113788716827 -0.000250975162291 -0.000113816215659  0.999999987521634 -0.000109556383190  0.000250962692879  0.000109584944073  0.999999962504433
18  0.999999823804258  0.000250836664770  0.000538026412754 -0.000251006915493  0.999999918445988  0.000316391444050 -0.000537947006302 -0.000316526436653  0.999999805211998
19  0.999999303029365  0.001137468474629 -0.000316395723295 -0.001137468565401  0.999999353082416 -0.000000106949082  0.000316395396962  0.000000466839196  0.999999949946866
20  0.999999926022649 -0.000376080720790 -0.000080734052208  0.000376080795916  0.999999929281196  0.000000915360977  0.000080733702249 -0.000000945723436  0.999999996740587
21  0.999998836362854 -0.000686860102809  0.001362165972411  0.000686392556656  0.999999705376305  0.000343675080446 -0.001362401627786 -0.000342739699949  0.999999013195165
22  0.999999347835282 -0.001108966409027 -0.000272988120637  0.001108746259287  0.999999061103236 -0.000805279069384  0.000273880891768  0.000804975869652  0.999999638501488
23  0.999999965116266  0.000218520448351 -0.000148378843028 -0.000218526636922  0.999999975253902 -0.000041692974441  0.000148369728589  0.000041725397716  0.999999988122707
24  0.999999992377253  0.000066780801720  0.000103854799570 -0.000066770676170  0.999999993017948 -0.000097497591715 -0.000103861309812  0.000097490656517  0.999999989854200
"""

if __name__=="__main__":
  channel_wavelength_fmodel(create=False)
  print("OK")

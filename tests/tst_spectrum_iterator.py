from __future__ import division, print_function
from six.moves import cPickle, range
import os
from libtbx.test_utils import approx_equal

from LS49 import ls49_big_data

def create_reference_results():
  from LS49.spectra.generate_spectra import spectra_simulation
  SS = spectra_simulation()
  iterator = SS.generate_recast_renormalized_images(20,energy=7120.,total_flux=1e12)
  results=[]
  #SS.plot_recast_images(20,7120.) # optionally plot these spectra
  for x in range(20):
    wavlen, flux, wavelength_A = next(iterator) # list of lambdas, list of fluxes, average wavelength
    results.append((wavlen, flux, wavelength_A))
  cPickle.dump(results,open(os.path.join(ls49_big_data,"reference","tst_spectrum_iterator_data"),"wb"),cPickle.HIGHEST_PROTOCOL)

def tst_iterators():
  from LS49.spectra.generate_spectra import spectra_simulation
  SS = spectra_simulation()
  import six
  if six.PY3:
    reference = cPickle.load(
      open(os.path.join(ls49_big_data,"reference","tst_spectrum_iterator_data"),"rb"),encoding="bytes")
  else:
    reference = cPickle.load(open(os.path.join(ls49_big_data,"reference","tst_spectrum_iterator_data"),"rb"))

  # use of single iterator with next()
  iterator = SS.generate_recast_renormalized_images(20,energy=7120.,total_flux=1e12)
  for x in range(20):
    wavlen, flux, wavelength_A = next(iterator) # list of lambdas, list of fluxes, average wavelength
    assert approx_equal(wavlen,reference[x][0]), "wavelength axis"
    assert approx_equal(flux, reference[x][1]), "flux axis"
    assert approx_equal(wavelength_A,reference[x][2],eps=1E-10), "mean wavelength"

  # get a new iterator for every event
  for x in range(10):
    iterator = SS.generate_recast_renormalized_image(image=x,energy=7120.,total_flux=1e12)
    wavlen, flux, wavelength_A = next(iterator) # list of lambdas, list of fluxes, average wavelength
    assert approx_equal(wavlen,reference[x][0]), "iterator 2 wavelength axis"
    assert approx_equal(flux, reference[x][1]), "iterator 2 flux axis"
    assert approx_equal(wavelength_A, reference[x][2],eps=1E-10), "iterator 2 mean wavelength"

if __name__=="__main__":
  # create_reference_results() # create the test case
  tst_iterators()
  print("OK")

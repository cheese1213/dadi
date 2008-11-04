import numpy
from numpy import newaxis as nuax

from scipy import comb
from scipy.special import gammaln

import Numerics
from Numerics import reverse_array, trapz
from scipy.integrate import trapz

def sfs_from_phi_1D(n, xx, phi):
    sfs = numpy.zeros(n+1)
    for ii in range(0,n+1):
        factorx = comb(n,ii) * xx**ii * (1-xx)**(n-ii)
        sfs[ii] = trapz(factorx * phi, xx)

    return sfs

def sfs_from_phi_2D(nx, ny, xx, yy, phi):
    # Calculate the 2D sfs from phi using the trapezoid rule for integration.
    sfs = numpy.zeros((nx+1, ny+1))
    
    # Cache to avoid duplicated work.
    factorx_cache = {}
    for ii in range(0, nx+1):
        factorx = comb(nx, ii) * xx**ii * (1-xx)**(nx-ii)
        factorx_cache[nx,ii] = factorx

    dx, dy = numpy.diff(xx), numpy.diff(yy)
    for jj in range(0,ny+1):
        factory = comb(ny, jj) * yy**jj * (1-yy)**(ny-jj)
        integrated_over_y = trapz(factory[numpy.newaxis,:]*phi, dx=dy)
        for ii in range(0, nx+1):
            factorx = factorx_cache[nx,ii]
            sfs[ii,jj] = trapz(factorx*integrated_over_y, dx=dx)

    return sfs

def sfs_from_phi_3D(nx, ny, nz, xx, yy, zz, phi):
    sfs = numpy.zeros((nx+1, ny+1, nz+1))

    dx, dy, dz = numpy.diff(xx), numpy.diff(yy), numpy.diff(zz)
    half_dx = dx/2.0

    # We cache these calculations...
    factorx_cache, factory_cache = {}, {}
    for ii in range(0, nx+1):
        factorx = comb(nx, ii) * xx**ii * (1-xx)**(nx-ii)
        factorx_cache[nx,ii] = factorx
    for jj in range(0, ny+1):
        factory = comb(ny, jj) * yy**jj * (1-yy)**(ny-jj)
        factory_cache[ny,jj] = factory[nuax,:]

    for kk in range(0, nz+1):
        factorz = comb(nz, kk) * zz**kk * (1-zz)**(nz-kk)
        over_z = trapz(factorz[nuax, nuax,:] * phi, dx=dz)
        for jj in range(0, ny+1):
            factory = factory_cache[ny,jj]
            over_y = trapz(factory * over_z, dx=dy)
            for ii in range(0, nx+1):
                factorx = factorx_cache[nx,ii]
                # It's faster here to do the trapezoid rule explicitly rather
                #  than using SciPy's more general routine.
                integrand = factorx * over_y
                ans = numpy.sum(half_dx * (integrand[1:]+integrand[:-1]))
                sfs[ii,jj,kk] = ans

    return sfs

def optimally_scaled_sfs(model, data):
    """
    Optimially scale model sfs to data sfs.

    Returns a new scaled model sfs.
    """
    return optimal_sfs_scaling(model,data) * model

def optimal_sfs_scaling(model, data):
    """
    Optimal multiplicative scaling factor between model and data.

    This scaling is based on only those entries that are masked in neither
    model nor data.
    """
    model, data = Numerics.intersect_masks(model, data)
    return data.sum()/model.sum()

def Fst(sfs):
    """
    Return Wright's Fst between the populations represented in the sfs.

    This estimate of Fst assumes random mating, because we don't have
    heterozygote frequencies in the sfs.

    Calculation is by the method of Weir and Cockerham _Evolution_ 38:1358. For
    a single SNP, the relevant formula is at the top of page 1363. To combine
    results between SNPs, we use the weighted average indicated by equation 10.
    """
    # This gets a little obscure because we want to be able to work with spectra
    # of arbitrary dimension.

    # First quantities from page 1360
    r = sfs.ndim
    ns = numpy.asarray(sfs.shape) - 1
    nbar = numpy.mean(ns)
    nsum = numpy.sum(ns)
    nc = (nsum - numpy.sum(ns**2)/nsum)/(r-1)

    # counts_per_pop is an r+1 dimensional array, where the last axis simply
    # records the indices of the entry. 
    # For example, counts_per_pop[4,19,8] = [4,19,8]
    counts_per_pop = numpy.indices(sfs.shape)
    counts_per_pop = numpy.transpose(counts_per_pop, axes=range(1,r+1)+[0])

    # The last axis of ptwiddle is now the relative frequency of SNPs in that
    # bin in each of the populations.
    ptwiddle = 1.*counts_per_pop/ns

    # Note that pbar is of the same shape as sfs...
    pbar = numpy.sum(ns*ptwiddle, axis=-1)/nsum

    # We need to use 'this_slice' to get the proper aligment between ptwiddle
    # and pbar.
    this_slice = [slice(None)]*r + [numpy.newaxis]
    s2 = numpy.sum(ns * (ptwiddle - pbar[this_slice])**2, axis=-1)/((r-1)*nbar)

    # Note that this 'a' differs from equation 2, because we've used equation 3
    # and b = 0 to solve for hbar.
    a = nbar/nc * (s2 - 1/(2*nbar-1) * (pbar*(1-pbar) - (r-1)/r*s2))
    d = 2*nbar/(2*nbar-1) * (pbar*(1-pbar) - (r-1)/r*s2)

    # The weighted sum over loci.
    asum = (sfs * a).sum()
    dsum = (sfs * d).sum()

    return asum/(asum+dsum)

def randomly_resampled_2D(sfs):
    """
    Randomly scramble individuals among the populations. 
    
    This is useful for measuring divergence. Essentially, this method pools all
    the individuals represented in the sfs and generates two new populations of
    random individuals (without replacement) from that pool.
    """
    n1,n2 = numpy.asarray(sfs.shape)-1
    ntot = n1+n2

    # First generate a 1d sfs for the pooled population.
    sfs_combined = numpy.zeros(ntot+1)
    for ii, row in enumerate(sfs):
        for jj, num_snps in enumerate(row):
            derived_total = ii+jj
            # This isscalar check deals with masking
            if numpy.isscalar(num_snps):
                sfs_combined[derived_total] += num_snps

    # Now resample
    sfs_resamp = numpy.zeros(sfs.shape)
    for derived1 in range(n1+1):
        for derived_total, num_snps in enumerate(sfs_combined):
            derived2 = derived_total - derived1
            ancestral_total = ntot - derived_total
            ancestral1 = n1 - derived1

            prob = numpy.exp(lncomb(derived_total, derived1)
                             + lncomb(ancestral_total, ancestral1)
                             - lncomb(ntot, n1))
            if prob > 0:
                sfs_resamp[derived1, derived2] += prob*num_snps
    return sfs_resamp

def mask_corners(sfs):
    """ 
    Return a masked SFS in which the 'absent in all pops' and 'fixed in all
    pops' entries are masked. These entries are often unobservable.
    """
    mask = numpy.ma.make_mask_none(sfs.shape)
    mask.flat[0] = mask.flat[-1] = True
    sfs = numpy.ma.masked_array(sfs, mask=mask)

    return sfs

def Watterson_theta(sfs):
    """
    Watterson's estimator of theta.

    Note that is only sensible for 1-dimensional spectra.
    """
    if sfs.ndim != 1:
        raise ValueError("Only defined on a one-dimensional SFS.")

    n = sfs.shape[0]-1
    S = mask_corners(sfs).sum()
    denom = numpy.sum(1./numpy.arange(1,n))

    return S/denom

def pi(sfs):
    """
    Estimated expected heterozygosity.

    Note that this estimate assumes a randomly mating population.
    """
    if sfs.ndim != 1:
        raise ValueError("Only defined on a one-dimensional SFS.")

    n = sfs.shape[0]-1
    # sample frequencies p 
    p = 1.*numpy.arange(0,n+1)/n
    return n/(n-1) * 2*numpy.ma.sum(sfs*p*(1-p))

def Tajima_D(sfs):
    """
    Tajima's D.

    Following Gillespie "Population Genetics: A Concise Guide" pg. 45
    """
    if not sfs.ndim == 1:
        raise ValueError("Only defined on a one-dimensional SFS.")

    S = mask_corners(sfs).sum()

    n = sfs.shape[0]-1.
    pihat = pi(sfs)
    theta = Watterson_theta(sfs)

    a1 = numpy.sum(1./numpy.arange(1,n))
    a2 = numpy.sum(1./numpy.arange(1,n)**2)
    b1 = (n+1)/(3*(n-1))
    b2 = 2*(n**2 + n + 3)/(9*n * (n-1))
    c1 = b1 - 1./a1
    c2 = b2 - (n+2)/(a1*n) + a2/a1**2

    C = numpy.sqrt((c1/a1)*S + c2/(a1**2 + a2) * S*(S-1))

    return (pihat - theta)/C

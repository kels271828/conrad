from numpy import ndarray, array, squeeze, zeros
from scipy.sparse import csr_matrix, csc_matrix
from conrad.dvh import DoseDensity, DVHCurve, DoseSummary
from conrad.defs import CONRAD_DEBUG_PRINT
# from tabulate import tabulate

# TODO: unit test
"""
TODO: structure.py docstring
"""

DOSE_DEFAULT = 1.
W_UNDER_DEFAULT = 1.
W_OVER_DEFAULT = 0.05
W_NONTARG_DEFAULT = 0.1

class Structure(object):
	""" TODO: docstring """
	def __init__(self, label, **options):
		""" TODO: docstring """
		# basic information
		self.label = label
		self.name = options['name'] if 'name' in options else ''
		self.is_target = options['is_target'] if 'is_target' in options else False

		# number of voxels in structure
		self.size = options['size'] if 'size' in options else None
		self.start_index = None
		self.stop_index = None

		# prescribed dose
		self.dose = options['dose'] if 'dose' in options else 0.
		if self.dose is not None:
			self.is_target = self.dose > 0 
		if self.is_target is not None:
			if self.is_target and self.dose is None:
				self.dose = DOSE_DEFAULT

		# dictionary of DoseConstraint objects attached to 
		# structure, keyed by constraint id (which is passed 
		# in by owner of Structure object).
		self.dose_constraints = {}
		
		# dose distribution using gaussian kernel
		self.dose_density = DoseDensity()

		# dvh curve and constraints data for plotting
		self.dvh_curve = DVHCurve()
		
		# summary statistics of dose on structure
		self.dose_summary = DoseSummary()

		# set (pointer to) subsection of dose matrix corresponding to structure
		self.set_A_full(options.pop('A', None))

		# set (pointer to) clustered version of same dose matrix
		self.set_A_clustered(options.pop('A_clustered', None), 
			options.pop('vox2cluster', None), options.pop('vox_per_cluster', None))

		# set (pointer to) fully compressed version of same dose matrix
		self.set_A_mean(options.pop('A_mean', None))

		# use full matrix by default
		self.switch_A(options.pop('representation', 'full'))


		# dose vector
		self._y = None
		self._y_mean = None

		# objective weights (set to defaults if not provided)
		self._w_under = options['w_under'] if 'w_under' in options else None
		self._w_over = options['w_over'] if 'w_over' in options else None
		if self.is_target is not None:
			if self.is_target:
				if self._w_under is None: 
					self._w_under = W_UNDER_DEFAULT
				if self._w_over is None:
					self._w_over = W_OVER_DEFAULT
			else:
				if self._w_over is None:
					self._w_over = W_NONTARG_DEFAULT


	def set_A_full(self, A_full):
		self.A_full = A_full

		# verify type of A_full
		if A_full is not None and not isinstance(
			self.A_full, (ndarray, csr_matrix, csc_matrix)):
			TypeError("input A must by a numpy or "
				"scipy csr/csc sparse matrix")

		# if A_full is a matrix, and self.A is not set, switch self.A to A_full
		if self.A_full is not None and self.A is None:
			self.switch_A()
		
	def set_A_mean(self, A_mean = None):
		if A_mean is not None:
			self.A_mean = A_mean
		elif self.A_full is not None:
			self.A_mean = self.A_full.sum(0) / self.A_full.shape[0]
			if not isinstance(self.A_full, ndarray):
				# (handling for sparse matrices)
				squeeze(array(self.A_full)) 

	def set_A_full_and_mean(self, A_full, A_mean = None):
		self.set_A_full(A_full)
		self.set_A_mean(A_mean)

	def set_A_clustered(self, A_clu, vox2cluster, vox_per_cluster):
		self.A_clu = A_clu
		self.v2c = vox2cluster
		if vox_per_cluster is not None:
			self.vpc = vox_per_cluster
		elif vox2cluster is not None:
			self.vpc = zeros(A_clu.shape[0])
			for cluster in enumerate(self.v2c):
				self.vpc[cluster] += 1
		else:
			self.vpc = None

	@property
	def __clustered_representation_exists(self):
		return self.A_clu is not None and self.v2c is not None and self.vpc is not None

	def switch_A(self, mat = 'full'):
		repstring = 'full'
		if mat == 'mean' and self.A_mean is not None:
			self.A = self.A_mean
			repstring = 'mean'
		elif mat == 'clustered' and self.__clustered_representation_exists:
			self.A = self.A_clu
			repstring = 'mean'
		else:
			if self.A_full is None: repstring = 'none'
			self.A = self.A_full

		CONRAD_DEBUG_PRINT( str('switched representation of structure {} ({}) '
			'to {}.\n'.format(self.label, self.name, repstring)) )


	def set_block_indices(self, idx_start, idx_stop):
		self.start_index = idx_start
		self.stop_index = idx_stop

	def set_objective(self, dose, w_under, w_over):
		if self.is_target:
			if dose is not None:
				self.dose = dose
			if w_under is not None:
				self.w_under = w_under
		if w_over is not None:
			self.w_over = w_over

	def set_constraint(self, constr_id, dose, fraction, direction):
		if self.has_constraint(constr_id):
			self.dose_constraints[constr_id].change(dose, fraction, direction)


	@property
	def w_under(self):
		""" TODO: docstring """
		if isinstance(self._w_under, (float, int)):
		    return self._w_under / float(self.size)
		else:
			return None
	
	@property
	def w_under_raw(self):
	    return self._w_under
	
	@property
	def w_over(self):
		""" TODO: docstring """
		if isinstance(self._w_over, (float, int)):
		    return self._w_over / float(self.size)
		else:
			return None
	
	@property
	def w_over_raw(self):
	    return self._w_under

	def calc_y(self, x):
		""" TODO: docstring """

		# calculate dose from input vector x:
		# 	y = Ax
		x = squeeze(array(x))
		if isinstance(self.A, (csr_matrix, csc_matrix)):
			self._y = squeeze(self.A * x)
		elif isinstance(self.A, ndarray):
			self._y = self.A.dot(x)

		self._y_mean = self.A_mean.dot(x)



		# make DVH curve from calculated dose
		self.dvh_curve.make(self._y)
		self.dose_density.make(self._y)
		self.dose_summary.make(self._y)

	def get_y(self, x):
		""" TODO: docstring """
		self.calc_y(x)
		return self._y

	@property
	def y(self):
		""" TODO: docstring """
		return self._y
	
	@property
	def mean_dose(self):
		""" TODO: docstring """
		return self._y_mean


	def has_constraint(self, constr_id):
		""" TODO: docstring """
		return constr_id in self.dose_constraints

	def remove_constraint(self, constr_id):
		""" TODO: docstring """
		if self.has_constraint(constr_id):
			del self.dose_constraints[constr_id]

	def add_constraint(self, constr_id, constr):
		""" TODO: docstring """
		self.dose_constraints[constr_id] = constr	

	def remove_all_constraints(self):
		""" TODO: docstring """
		for cid in self.dose_constraints:
			del self.dose_constraints[cid]

	@property
	def plotting_data(self):
		""" TODO: docstring """
		d = {}
		d['density'] = self.dose_density.plotting_data
		d['curve'] = self.dvh_curve.plotting_data
		d['constraints'] = [dc.plotting_data for dc in self.dose_constraints.itervalues()]
		return d
	
	def summary(self):
		print self.dose_summary.table_data
		# print tabulate([self.dose_summary.table_data], headers = "keys", tablefmt = "pipe")

	def __header_string(self):
		""" TODO: docstring """
		out = 'Structure: {}'.format(self.label)
		if self.name != '':
			out += " ({})".format(self.name)
			out += "\n"
		return out		

	def __obj_string(self):
		""" TODO: docstring """
		out = "target? {}\n".format(self.is_target)
		out += "rx dose: {}\n".format(self.dose)
		if self.is_target:
			out += "weight_under: {}\n".format(self._w_under)
			out += "weight_over: {}\n".format(self._w_over)			
		else:
			out += "weight: {}\n".format(self._w_over)
		out += "\n"		
		return out

	def __constr_string(self):
		""" TODO: docstring """
		out = ""
		for dc in self.dose_constraints.itervalues():
			out += dc.__str__()
		out += "\n"
		return out

	@property
	def objective_string(self):
		""" TODO: docstring """
		return self.__header_string + self.__obj_string

	@property
	def constraints_string(self):
		""" TODO: docstring """
		return self.__header_string + self.__constr_string

	def __str__(self):
		return self.__header_string + self.__obj_string + self.__constr_string

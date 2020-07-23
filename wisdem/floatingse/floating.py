import openmdao.api as om
from wisdem.floatingse.column import Column, ColumnGeometry
from wisdem.floatingse.substructure import Substructure, SubstructureGeometry
from wisdem.floatingse.loading import Loading
from wisdem.floatingse.map_mooring import MapMooring
from wisdem.towerse.tower import TowerLeanSE
import numpy as np

from wisdem.commonse.vertical_cylinder import get_nfull


class FloatingSE(om.Group):

    def initialize(self):
        self.options.declare('analysis_options')
        self.options.declare('topLevelFlag', default=True)

    def setup(self):
        opt = self.options['analysis_options']['platform']
        n_mat = self.options['analysis_options']['materials']['n_mat']
        n_height_main = opt['columns']['main']['n_height']
        n_height_off  = opt['columns']['offset']['n_height']
        n_height_tow  = self.options['analysis_options']['tower']['n_height']
        topLevelFlag  = self.options['topLevelFlag']

        # Define all input variables from all models
        ivc = om.IndepVarComp()
        
        # SemiGeometry
        ivc.add_output('radius_to_offset_column', 0.0, units='m')
        ivc.add_output('number_of_offset_columns', 0)
        
        ivc.add_output('fairlead_location', 0.0)
        ivc.add_output('fairlead_offset_from_shell', 0.0, units='m')
        ivc.add_output('max_draft', 0.0, units='m')
        ivc.add_output('main_freeboard', 0.0, units='m') # Have to add here because cannot promote ivc from Column before needed by tower.  Grr
        ivc.add_output('offset_freeboard', 0.0, units='m')

        # Mooring
        ivc.add_output('mooring_line_length', 0.0, units='m')
        ivc.add_output('anchor_radius', 0.0, units='m')
        ivc.add_output('mooring_diameter', 0.0, units='m')
        ivc.add_output('number_of_mooring_connections', 0)
        ivc.add_output('mooring_lines_per_connection', 0)
        ivc.add_discrete_output('mooring_type', 'chain')
        ivc.add_discrete_output('anchor_type', 'SUCTIONPILE')
        ivc.add_output('max_offset', 0.0, units='m')
        ivc.add_output('operational_heel', 0.0, units='deg')
        ivc.add_output('mooring_cost_factor', 0.0)
        ivc.add_output('max_survival_heel', 0.0, units='deg')

        # Column
        ivc.add_output('permanent_ballast_density', 0.0, units='kg/m**3')
        ivc.add_output('outfitting_factor', 0.0)
        ivc.add_output('ballast_cost_rate', 0.0, units='USD/kg')
        ivc.add_output('unit_cost_mat', 0.0, units='USD/kg')
        ivc.add_output('labor_cost_rate', 0.0, units='USD/min')
        ivc.add_output('painting_cost_rate', 0.0, units='USD/m**2')
        ivc.add_output('outfitting_cost_rate', 0.0, units='USD/kg')
        ivc.add_discrete_output('loading', 'hydrostatic')
        
        ivc.add_output('max_taper_ratio', 0.0)
        ivc.add_output('min_diameter_thickness_ratio', 0.0)

        # Other Constraints
        ivc.add_output('wave_period_range_low', 2.0, units='s')
        ivc.add_output('wave_period_range_high', 20.0, units='s')
        self.add_subsystem('ivc', ivc, promotes=['*'])

        # Independent variables that may be duplicated at higher levels of aggregation
        if topLevelFlag:
            sharedIndeps = om.IndepVarComp()
            sharedIndeps.add_output('hub_height', 0.0, units='m')
            sharedIndeps.add_output('rho_air', 0.0, units='kg/m**3')
            sharedIndeps.add_output('mu_air', 0.0, units='kg/m/s')
            sharedIndeps.add_output('shearExp', 0.0)
            sharedIndeps.add_output('wind_reference_height', 0.0, units='m')
            sharedIndeps.add_output('wind_reference_speed', 0.0, units='m/s')
            sharedIndeps.add_output('wind_z0', 0.0, units='m')
            sharedIndeps.add_output('beta_wind', 0.0, units='deg')
            sharedIndeps.add_output('cd_usr', -1.0)
            sharedIndeps.add_output('cm', 0.0)
            sharedIndeps.add_output('Uc', 0.0, units='m/s')
            sharedIndeps.add_output('water_depth', 0.0, units='m')
            sharedIndeps.add_output('rho_water', 0.0, units='kg/m**3')
            sharedIndeps.add_output('mu_water', 0.0, units='kg/m/s')
            sharedIndeps.add_output('hsig_wave', 0.0, units='m')
            sharedIndeps.add_output('Tsig_wave', 0.0, units='s')
            sharedIndeps.add_output('beta_wave', 0.0, units='deg')
            sharedIndeps.add_output('wave_z0', 0.0, units='m')
            sharedIndeps.add_output('yaw', 0.0, units='deg')
            sharedIndeps.add_output('rho_mat', np.zeros(1), units='kg/m**3')
            sharedIndeps.add_output('E_mat', np.zeros((1,3)), units='N/m**2')
            sharedIndeps.add_output('G_mat', np.zeros((1,3)), units='N/m**2')
            sharedIndeps.add_output('sigma_y_mat', np.zeros(1), units='N/m**2')
            sharedIndeps.add_output('DC', 0.0)
            sharedIndeps.add_output('life', 0.0)
            sharedIndeps.add_output('m_SN', 0.0)
            sharedIndeps.add_output('rna_mass', 0.0, units='kg')
            sharedIndeps.add_output('rna_I', np.zeros(6), units='kg*m**2')
            sharedIndeps.add_output('rna_cg', np.zeros(3), units='m')
            sharedIndeps.add_discrete_output('material_names', ['steel'])
            self.add_subsystem('sharedIndeps', sharedIndeps, promotes=['*'])

        
        self.add_subsystem('tow', TowerLeanSE(analysis_options=self.options['analysis_options'], topLevelFlag=False),
                           promotes=['tower_s','tower_height','tower_outer_diameter_in','tower_layer_thickness','tower_outfitting_factor',
                                     'max_taper','min_d_to_t','rna_mass','rna_cg','rna_I',
                                     'tower_mass','tower_I_base','hub_height','material_names',
                                     'labor_cost_rate','painting_cost_rate','unit_cost_mat','rho_mat','E_mat','G_mat','sigma_y_mat'])
        
        # Next do main and ballast columns
        # Ballast columns are replicated from same design in the components
        column_promotes = ['E_mat','G_mat','sigma_y_mat','z0','rho_air','mu_air','rho_water','mu_water','rho_mat',
                           'Uref','zref','shearExp','yaw','Uc','water_depth',
                           'hsig_wave','Tsig_wave','cd_usr','cm','loading','beta_wind','beta_wave',
                           'max_draft','max_taper','min_d_to_t','material_names',
                           'permanent_ballast_density','outfitting_factor','ballast_cost_rate',
                           'unit_cost_mat','labor_cost_rate','painting_cost_rate','outfitting_cost_rate']
        
        self.add_subsystem('main', Column(analysis_options=opt, column_options=opt['columns']['main'], n_mat=n_mat, topLevelFlag=False),
                           promotes=column_promotes)

        self.add_subsystem('off', Column(analysis_options=opt, column_options=opt['columns']['offset'], n_mat=n_mat, topLevelFlag=False),
                           promotes=column_promotes)

        # Run Semi Geometry for interfaces
        self.add_subsystem('sg', SubstructureGeometry(n_height_main=n_height_main,
                                                      n_height_off=n_height_off), promotes=['*'])

        # Next run MapMooring
        self.add_subsystem('mm', MapMooring(analysis_options=opt), promotes=['*'])
        
        # Add in the connecting truss
        self.add_subsystem('load', Loading(n_height_main=n_height_main,
                                           n_height_off=n_height_off,
                                           n_height_tow=n_height_tow,
                                           analysis_options=opt), promotes=['*'])

        # Run main Semi analysis
        self.add_subsystem('subs', Substructure(n_height_main=n_height_main,
                                                n_height_off=n_height_off,
                                                n_height_tow=n_height_tow), promotes=['*'])
        
        # Connect all input variables from all models
        self.connect('main_freeboard', ['tow.foundation_height','main.freeboard','tow.transition_piece_height'])
        self.connect('offset_freeboard', 'off.freeboard')

        self.connect('tow.d_full', ['windLoads.d','tower_d_full'])
        self.connect('tow.d_full', 'tower_d_base', src_indices=[0])
        self.connect('tow.t_full', 'tower_t_full')
        self.connect('tow.z_full', ['loadingWind.z','windLoads.z','tower_z_full']) # includes tower_z_full
        self.connect('tow.E_full', 'tower_E_full')
        self.connect('tow.G_full', 'tower_G_full')
        self.connect('tow.rho_full', 'tower_rho_full')
        self.connect('tow.sigma_y_full', 'tower_sigma_y_full')
        self.connect('tow.cm.mass','tower_mass_section')
        self.connect('tow.turbine_mass','main.stack_mass_in')
        self.connect('tow.tower_center_of_mass','tower_center_of_mass')
        self.connect('tow.tower_raw_cost','tower_shell_cost')
        
        self.connect('max_taper_ratio', 'max_taper')
        self.connect('min_diameter_thickness_ratio', 'min_d_to_t')
        
        # To do: connect these to independent variables
        if topLevelFlag:
            self.connect('water_depth',['main.wave.z_floor','off.wave.z_floor'])
            self.connect('wave_z0',['main.wave.z_surface','off.wave.z_surface'])
            self.connect('wind_z0','z0')
            self.connect('wind_reference_height','zref')
            self.connect('wind_reference_speed','Uref')
            
        
        self.connect('main.z_full', ['main_z_nodes', 'main_z_full'])
        self.connect('main.d_full', 'main_d_full')
        self.connect('main.t_full', 'main_t_full')
        self.connect('main.E_full', 'main_E_full')
        self.connect('main.G_full', 'main_G_full')
        self.connect('main.rho_full', 'main_rho_full')
        self.connect('main.sigma_y_full', 'main_sigma_y_full')

        self.connect('off.z_full', ['offset_z_nodes', 'offset_z_full'])
        self.connect('off.d_full', 'offset_d_full')
        self.connect('off.t_full', 'offset_t_full')
        self.connect('off.E_full', 'offset_E_full')
        self.connect('off.G_full', 'offset_G_full')
        self.connect('off.rho_full', 'offset_rho_full')
        self.connect('off.sigma_y_full', 'offset_sigma_y_full')

        self.connect('max_offset_restoring_force', 'mooring_surge_restoring_force')
        self.connect('operational_heel_restoring_force', 'mooring_pitch_restoring_force')
        
        self.connect('main.z_center_of_mass', 'main_center_of_mass')
        self.connect('main.z_center_of_buoyancy', 'main_center_of_buoyancy')
        self.connect('main.I_column', 'main_moments_of_inertia')
        self.connect('main.Iwater', 'main_Iwaterplane')
        self.connect('main.Awater', 'main_Awaterplane')
        self.connect('main.displaced_volume', 'main_displaced_volume')
        self.connect('main.hydrostatic_force', 'main_hydrostatic_force')
        self.connect('main.column_added_mass', 'main_added_mass')
        self.connect('main.column_total_mass', 'main_mass')
        self.connect('main.column_total_cost', 'main_cost')
        self.connect('main.variable_ballast_interp_zpts', 'water_ballast_zpts_vector')
        self.connect('main.variable_ballast_interp_radius', 'water_ballast_radius_vector')
        self.connect('main.Px', 'main_Px')
        self.connect('main.Py', 'main_Py')
        self.connect('main.Pz', 'main_Pz')
        self.connect('main.qdyn', 'main_qdyn')

        self.connect('off.z_center_of_mass', 'offset_center_of_mass')
        self.connect('off.z_center_of_buoyancy', 'offset_center_of_buoyancy')
        self.connect('off.I_column', 'offset_moments_of_inertia')
        self.connect('off.Iwater', 'offset_Iwaterplane')
        self.connect('off.Awater', 'offset_Awaterplane')
        self.connect('off.displaced_volume', 'offset_displaced_volume')
        self.connect('off.hydrostatic_force', 'offset_hydrostatic_force')
        self.connect('off.column_added_mass', 'offset_added_mass')
        self.connect('off.column_total_mass', 'offset_mass')
        self.connect('off.column_total_cost', 'offset_cost')
        self.connect('off.Px', 'offset_Px')
        self.connect('off.Py', 'offset_Py')
        self.connect('off.Pz', 'offset_Pz')
        self.connect('off.qdyn', 'offset_qdyn')
        self.connect('off.draft', 'offset_draft')




def commonVars(prob, nsection):
    # Variables common to both examples

    # Set environment to that used in OC4 testing campaign
    prob['shearExp']    = 0.11   # Shear exponent in wind power law
    prob['cm']          = 2.0    # Added mass coefficient
    prob['Uc']          = 0.0    # Mean current speed
    prob['wind_z0']     = 0.0    # Water line
    prob['yaw']         = 0.0    # Turbine yaw angle
    prob['beta_wind'] = prob['beta_wave'] = 0.0    # Wind/water beta angle
    prob['cd_usr']      = -1.0 # Compute drag coefficient

    # Wind and water properties
    prob['rho_air'] = 1.226   # Density of air [kg/m^3]
    prob['mu_air']  = 1.78e-5 # Viscosity of air [kg/m/s]
    prob['rho_water']      = 1025.0  # Density of water [kg/m^3]
    prob['mu_water']  = 1.08e-3 # Viscosity of water [kg/m/s]
    
    # Material properties
    prob['rho_mat']     = np.array([7850.0])          # Steel [kg/m^3]
    prob['E_mat']       = 200e9*np.ones((1,3))           # Young's modulus [N/m^2]
    prob['G_mat']       = 79.3e9*np.ones((1,3))          # Shear modulus [N/m^2]
    prob['sigma_y_mat'] = np.array([3.45e8])          # Elastic yield stress [N/m^2]
    prob['permanent_ballast_density'] = 4492.0 # [kg/m^3]

    # Mass and cost scaling factors
    prob['outfitting_factor'] = 0.06    # Fraction of additional outfitting mass for each column
    prob['ballast_cost_rate']        = 0.1   # Cost factor for ballast mass [$/kg]
    prob['unit_cost_mat']       = np.array([1.1])  # Cost factor for column mass [$/kg]
    prob['labor_cost_rate']          = 1.0  # Cost factor for labor time [$/min]
    prob['painting_cost_rate']       = 14.4  # Cost factor for column surface finishing [$/m^2]
    prob['outfitting_cost_rate']     = 1.5*1.1  # Cost factor for outfitting mass [$/kg]
    prob['mooring_cost_factor']      = 1.1     # Cost factor for mooring mass [$/kg]
    
    # Mooring parameters
    prob['number_of_mooring_connections'] = 3             # Evenly spaced around structure
    prob['mooring_lines_per_connection'] = 1             # Evenly spaced around structure
    prob['mooring_type']               = 'chain'       # Options are chain, nylon, polyester, fiber, or iwrc
    prob['anchor_type']                = 'DRAGEMBEDMENT' # Options are SUCTIONPILE or DRAGEMBEDMENT
    
    # Porperties of turbine tower
    nTower = prob.model.options['analysis_options']['tower']['n_height']-1
    prob['tower_height']            = prob['hub_height'] = 77.6       # Length from tower main to top (not including freeboard) [m]
    prob['tower_s']                 = np.linspace(0.0, 1.0, nTower+1)
    prob['tower_outer_diameter_in'] = np.linspace(6.5, 3.87, nTower+1) # Diameter at each tower section node (linear lofting between) [m]
    prob['tower_layer_thickness']   = np.linspace(0.027, 0.019, nTower).reshape((1,nTower)) # Diameter at each tower section node (linear lofting between) [m]
    prob['tower_outfitting_factor'] = 1.07                              # Scaling for unaccounted tower mass in outfitting

    # Materials
    prob['material_names'] = ['steel']
    prob['main.layer_materials'] = prob['off.layer_materials'] = prob['tow.tower_layer_materials'] = ['steel']
    
    # Properties of rotor-nacelle-assembly (RNA)
    prob['rna_mass']   = 350e3 # Mass [kg]
    prob['rna_I']      = 1e5*np.array([1149.307, 220.354, 187.597, 0, 5.037, 0]) # Moment of intertia (xx,yy,zz,xy,xz,yz) [kg/m^2]
    prob['rna_cg']     = np.array([-1.132, 0, 0.509])                       # Offset of RNA center of mass from tower top (x,y,z) [m]
    # Max thrust
    prob['rna_force']  = np.array([1284744.196, 0, -112400.5527])           # Net force acting on RNA (x,y,z) [N]
    prob['rna_moment'] = np.array([3963732.762, 896380.8464, -346781.682]) # Net moment acting on RNA (x,y,z) [N*m]
    # Max wind speed
    #prob['rna_force']  = np.array([188038.8045, 0,  -16451.2637]) # Net force acting on RNA (x,y,z) [N]
    #prob['rna_moment'] = np.array([0.0, 131196.8431,  0.0]) # Net moment acting on RNA (x,y,z) [N*m]
    
    # Mooring constraints
    prob['max_draft'] = 150.0 # Max surge/sway offset [m]      
    prob['max_offset'] = 100.0 # Max surge/sway offset [m]      
    prob['operational_heel']   = 10.0 # Max heel (pitching) angle [deg]

    # Design constraints
    prob['max_taper_ratio'] = 0.2                # For manufacturability of rolling steel
    prob['min_diameter_thickness_ratio'] = 120.0 # For weld-ability
    prob['connection_ratio_max']      = 0.25 # For welding pontoons to columns

    # API 2U flag
    prob['loading'] = 'hydrostatic'
    
    return prob


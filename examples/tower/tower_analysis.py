# TODO: Code commenting and RST parallel
# TODO: Already an example in TowerSE documentation, use that?

# Tower analysis
# Optimization by flag
# Two load cases
import numpy as np
import openmdao.api as om
from wisdem.towerse.tower import TowerSE

plot_flag = True
opt_flag  = True

n_control_points = 3
n_materials      = 1
n_load_cases     = 2

# --- Geometry starting point -----
h_param = np.diff(np.linspace(0.0, 87.6, n_control_points))
d_param = np.linspace(6.0, 3.87, n_control_points)
t_param = 1.3*np.linspace(0.025, 0.021, n_control_points-1)
max_diam = 8.0

# Store analysis options
analysis_options = {}
analysis_options['materials'] = {}
analysis_options['monopile'] = {}
analysis_options['tower'] = {}
analysis_options['tower']['buckling_length'] = 30.0
analysis_options['tower']['monopile'] = False

# --- safety factors ---
analysis_options['tower']['gamma_f'] = 1.35
analysis_options['tower']['gamma_m'] = 1.3
analysis_options['tower']['gamma_n'] = 1.0
analysis_options['tower']['gamma_b'] = 1.1
analysis_options['tower']['gamma_fatigue'] = 1.35*1.3*1.0
# ---------------

# -----Frame3DD------
analysis_options['tower']['frame3dd']            = {}
analysis_options['tower']['frame3dd']['DC']      = 80.0
analysis_options['tower']['frame3dd']['shear']   = True
analysis_options['tower']['frame3dd']['geom']    = True
analysis_options['tower']['frame3dd']['dx']      = 5.0
analysis_options['tower']['frame3dd']['Mmethod'] = 1
analysis_options['tower']['frame3dd']['lump']    = 0
analysis_options['tower']['frame3dd']['tol']     = 1e-9
analysis_options['tower']['frame3dd']['shift']   = 0.0
analysis_options['tower']['frame3dd']['add_gravity'] = True
# ---------------

analysis_options['tower']['n_height'] = n_control_points
analysis_options['tower']['n_layers'] = 1
analysis_options['monopile']['n_height'] = 0
analysis_options['monopile']['n_layers'] = 0
analysis_options['tower']['wind'] = 'PowerWind'
analysis_options['tower']['nLC'] = n_load_cases
analysis_options['materials']['n_mat'] = n_materials

prob = om.Problem()
prob.model = TowerSE(analysis_options=analysis_options, topLevelFlag=True)

if opt_flag:
    prob.driver = om.ScipyOptimizeDriver()
    prob.driver.options['optimizer'] = 'SLSQP'

    # --- Objective ---
    prob.model.add_objective('tower_mass', scaler=1e-6)
    # ----------------------

    prob.model.add_design_var('tower_outer_diameter_in', lower=3.87, upper=max_diam)
    prob.model.add_design_var('tower_layer_thickness', lower=4e-3, upper=2e-1)

    # --- Constraints ---
    #prob.model.add_constraint('height_constraint',    lower=-1e-2,upper=1.e-2)
    prob.model.add_constraint('post1.stress',          upper=1.0)
    prob.model.add_constraint('post1.global_buckling', upper=1.0)
    prob.model.add_constraint('post1.shell_buckling',  upper=1.0)
    prob.model.add_constraint('post2.stress',          upper=1.0)
    prob.model.add_constraint('post2.global_buckling', upper=1.0)
    prob.model.add_constraint('post2.shell_buckling',  upper=1.0)
    prob.model.add_constraint('weldability',           upper=0.0)
    prob.model.add_constraint('manufacturability',     lower=0.0)
    prob.model.add_constraint('slope',                 upper=1.0)
    prob.model.add_constraint('tower1.f1',             lower=0.13, upper=0.40)
    prob.model.add_constraint('tower2.f1',             lower=0.13, upper=0.40)
    # ----------------------

prob.setup()


# --- geometry ----
prob['hub_height'] = prob['tower_height'] = h_param.sum()
prob['foundation_height'] = 0.0
prob['tower_s'] = np.cumsum(np.r_[0.0, h_param]) / h_param.sum()
prob['tower_outer_diameter_in'] = d_param
prob['tower_layer_thickness'] = t_param.reshape( (1,-1) )
prob['tower_outfitting_factor'] = 1.07
prob['yaw'] = 0.0

# --- offshore specific ----
prob['suctionpile_depth'] = 0.0
prob['suctionpile_depth_diam_ratio'] = 3.25
prob['G_soil'] = 140e6
prob['nu_soil'] = 0.4

# --- material properties ---
prob['E_mat'] = 210e9  * np.ones((n_materials,3))
prob['G_mat'] = 80.8e9 * np.ones((n_materials,3))
prob['rho_mat'] = [8500.0]
prob['sigma_y_mat'] = [450e6]

# --- extra mass ----
prob['rna_mass'] = np.array([285598.8])
mIxx = 1.14930678e+08
mIyy = 2.20354030e+07
mIzz = 1.87597425e+07
mIxy = 0.0
mIxz = 5.03710467e+05
mIyz = 0.0
prob['rna_I'] = np.array([mIxx, mIyy, mIzz, mIxy, mIxz, mIyz])
prob['rna_cg'] = np.array([-1.13197635, 0.0, 0.50875268])
# -----------

# --- costs ---
prob['unit_cost_mat']     = [2.0] # USD/kg
prob['labor_cost_rate']    = 100.0/60.0 # USD/min
prob['painting_cost_rate'] = 30.0 # USD/m^2
# -----------

# --- wind & wave ---
prob['wind_reference_height'] = 90.0
prob['wind_z0']   = 0.0
prob['cd_usr']    = -1.0
prob['rho_air']   = 1.225
prob['mu_air']    = 1.7934e-5
prob['rho_water'] = 1025.0
prob['mu_water']  = 1.3351e-3
prob['hsig_wave'] = 0.0
prob['Tsig_wave'] = 1.0
prob['beta_wind'] = prob['beta_wave'] = 0.0
if analysis_options['tower']['wind'] == 'PowerWind':
    prob['shearExp'] = 0.2
# -----------



# two load cases.  TODO: use a case iterator

# # --- loading case 1: max Thrust ---
prob['wind1.Uref'] = 11.73732
Fx1  = 1284744.19620519
Fy1  = 0.
Fz1  = -2914124.84400512 + prob['rna_mass']*9.81
Mxx1 = 3963732.76208099
Myy1 = -2275104.79420872
Mzz1 = -346781.68192839
prob['pre1.rna_F'] = np.array([Fx1, Fy1, Fz1])
prob['pre1.rna_M'] = np.array([Mxx1, Myy1, Mzz1])
# # ---------------

# # --- loading case 2: max Wind Speed ---
prob['wind2.Uref'] = 70.0
Fx2 = 930198.60063279
Fy2 = 0.
Fz2 = -2883106.12368949 + prob['rna_mass']*9.81
Mxx2 = -1683669.22411597
Myy2 = -2522475.34625363
Mzz2 = 147301.97023764
prob['pre2.rna_F'] = np.array([Fx2, Fy2, Fz2])
prob['pre2.rna_M' ] = np.array([Mxx2, Myy2, Mzz2])
# # ---------------

# --- constraints ---
prob['min_d_to_t'] = 120.0
prob['max_taper'] = 0.2
# ---------------


# # --- run ---
prob.model.approx_totals()
prob.run_driver()
prob.run_model()


z = 0.5*(prob['z_full'][:-1] + prob['z_full'][1:])

print('zs =', z)
print('ds =', prob['d_full'])
print('ts =', prob['t_full'])
print('mass (kg) =', prob['tower_mass'])
print('cg (m) =', prob['tower_center_of_mass'])
print('weldability =', prob['weldability'])
print('manufacturability =', prob['manufacturability'])
print('\nwind: ', prob['wind1.Uref'])
print('freq (Hz) =', prob['post1.structural_frequencies'])
print('Fore-aft mode shapes =', prob['post1.fore_aft_modes'])
print('Side-side mode shapes =', prob['post1.side_side_modes'])
print('top_deflection1 (m) =', prob['post1.top_deflection'])
print('Tower base forces1 (N) =', prob['tower1.base_F'])
print('Tower base moments1 (Nm) =', prob['tower1.base_M'])
print('stress1 =', prob['post1.stress'])
print('GL buckling =', prob['post1.global_buckling'])
print('Shell buckling =', prob['post1.shell_buckling'])
print('\nwind: ', prob['wind2.Uref'])
print('freq (Hz) =', prob['post2.structural_frequencies'])
print('Fore-aft mode shapes =', prob['post2.fore_aft_modes'])
print('Side-side mode shapes =', prob['post2.side_side_modes'])
print('top_deflection2 (m) =', prob['post2.top_deflection'])
print('Tower base forces2 (N) =', prob['tower2.base_F'])
print('Tower base moments2 (Nm) =', prob['tower2.base_M'])
print('stress2 =', prob['post2.stress'])
print('GL buckling =', prob['post2.global_buckling'])
print('Shell buckling =', prob['post2.shell_buckling'])


stress1 = np.copy( prob['post1.stress'] )
shellBuckle1 = np.copy( prob['post1.shell_buckling'] )
globalBuckle1 = np.copy( prob['post1.global_buckling'] )

stress2 = prob['post2.stress']
shellBuckle2 = prob['post2.shell_buckling']
globalBuckle2 = prob['post2.global_buckling']

if plot_flag:
    import matplotlib.pyplot as plt
    '''
    from matplotlib import rcParams
    import matplotlib.colorbar as cbar
    from matplotlib import cm
    
    # Pretty geometry plot
    scaling_factor = 10.
    
    global_buckling = np.hstack((prob['post1.global_buckling'], prob['post1.global_buckling'][-1]))
    shell_buckling = np.hstack((prob['post1.shell_buckling'], prob['post1.shell_buckling'][-1]))
    buc_tower = np.maximum(global_buckling, shell_buckling)
    
    D_tower = prob['tower_outer_diameter']
    wt_tower = np.hstack((prob['tower_wall_thickness'], prob['tower_wall_thickness'][-1]))
    stress = np.hstack((prob['post1.stress'], prob['post1.stress'][-1]))
    L_tower = prob['tower_section_height']

    X = np.zeros((n_control_points, 2))
    Z = np.zeros((n_control_points, 2))
    Cl = np.zeros((n_control_points, 2))
    Cr = np.zeros((n_control_points, 2))

    X[:, 0] = -D_tower / 2.
    X[:, 1] = -D_tower / 2. + scaling_factor * wt_tower
    Z[:, 0] = Z[:, 1] = L_tower.sum()
    Cl[:, 0] = Cl[:, 1] = stress.max()
    Cr[:, 0] = Cr[:, 1] = buc_tower.max()

    X0 = []
    Z0 = []

    X0 = np.hstack((-D_tower / 2., D_tower[::-1] / 2.))
    Z0 = np.hstack((L_tower, L_tower[::-1]))

    cmap = cm.viridis

    rcParams.update({'font.size': 18})

    fig, ax = plt.subplots(1, figsize=(8,12))

    ax.fill(X0, Z0, color='grey', zorder=0)
    ax.plot([-20., 20.], [0., 0.], color='k', linewidth=1.0, zorder=20)
    
    ax.plot([-max_diam/2., -max_diam/2.], [0., L_tower[-1]], color='r', alpha=0.5, lw=3., solid_capstyle='butt')
    ax.plot([max_diam/2., max_diam/2.], [0., L_tower[-1]], color='r', alpha=0.5, lw=3., solid_capstyle='butt')
    
    vmin = 0.5
    vmax = 1.1
    im = ax.pcolormesh(X, Z, Cl, cmap=cmap, vmin=vmin, vmax=vmax, shading='gouraud', zorder=10)
    im2 = ax.pcolormesh(-X, Z, Cr, cmap=cmap, vmin=vmin, vmax=vmax, shading='gouraud', zorder=10)
    
    print()
    print(X.shape, Z.shape, Cr.shape)
    if np.any(Cr > 1.01):
        im3 = ax.contour(-X, Z, Cr, levels=[0., 1.01, 2.], colors='black', zorder=15, linewidths=3)
    
    cbar = fig.colorbar(im, cmap=cmap, fraction=0.05, aspect=40, pad=0.1)
    cbar.set_label('Utilization', rotation=90)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    ax.set_xlim(-5., 5.)
    ax.set_ylim(-10., 150.)
    
    ax.annotate('Stress', xy=(X[-1, 0], 130), va="center", color='k', xycoords='data', xytext=(-4.25, 145), textcoords='data', arrowprops=dict(arrowstyle='-', lw=2))
    
    ax.annotate('Buckling', xy=(-X[-1, 0], 130), va="center", color='k', xycoords='data', xytext=(2.25, 145), textcoords='data', arrowprops=dict(arrowstyle='-', lw=2))
    
    plt.xlabel('Distance from center [m]')
    plt.ylabel('Elevation relative to ground [m]')
    
    plt.show()
    '''
    

    # Old line plot
    plt.figure(figsize=(5.0, 3.5))
    plt.subplot2grid((3, 3), (0, 0), colspan=2, rowspan=3)
    plt.plot(stress1, z, label='stress 1')
    plt.plot(stress2, z, label='stress 2')
    plt.plot(shellBuckle1, z, label='shell buckling 1')
    plt.plot(shellBuckle2, z, label='shell buckling 2')
    plt.plot(globalBuckle1, z, label='global buckling 1')
    plt.plot(globalBuckle2, z, label='global buckling 2')
    plt.legend(bbox_to_anchor=(1.05, 1.0), loc=2)
    plt.xlabel('utilization')
    plt.ylabel('height along tower (m)')
    plt.show()
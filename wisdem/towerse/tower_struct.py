import numpy as np
import openmdao.api as om
import wisdem.commonse.utilities as util
import wisdem.pyframe3dd.pyframe3dd as pyframe3dd
import wisdem.commonse.utilization_dnvgl as util_dnvgl
import wisdem.commonse.utilization_eurocode as util_euro
import wisdem.commonse.utilization_constraints as util_con
from wisdem.towerse import NFREQ, RIGID, NPTS_SOIL, gravity, get_nfull
from wisdem.commonse.utilization_eurocode import hoopStressEurocode
from wisdem.commonse.utilization_constraints import hoopStress


class TowerPreFrame(om.ExplicitComponent):
    """
    Compute some properties of the tower needed for FEM analysis.

    This component can be simplified by using src_indices for data-passing.
    At the very least, we can code the sparse derivatives as-is for
    input-output relationships.

    Parameters
    ----------
    z_full : numpy array[nFull], [m]
        location along tower. start at bottom and go to top
    mass : float, [kg]
        added mass
    mI : numpy array[6], [kg*m**2]
        mass moment of inertia about some point p [xx yy zz xy xz yz]
    mrho : numpy array[3], [m]
        xyz-location of p relative to node
    transition_piece_mass : float, [kg]
        point mass of transition piece
    gravity_foundation_mass : float, [kg]
        point mass of transition piece
    transition_piece_height : float, [m]
        height of transition piece above water line
    rna_F : numpy array[3], [N]
        rna force
    rna_M : numpy array[3], [N*m]
        rna moment
    k_monopile : numpy array[6], [N/m]
        Stiffness BCs for ocean soil. Only used if monoflag inputis True

    Returns
    -------
    kidx : numpy array[np.int_]
        indices of z where external stiffness reactions should be applied.
    kx : numpy array[nK], [N/m]
        spring stiffness in x-direction
    ky : numpy array[nK], [N/m]
        spring stiffness in y-direction
    kz : numpy array[nK], [N/m]
        spring stiffness in z-direction
    ktx : numpy array[nK], [N/m]
        spring stiffness in theta_x-rotation
    kty : numpy array[nK], [N/m]
        spring stiffness in theta_y-rotation
    ktz : numpy array[nK], [N/m]
        spring stiffness in theta_z-rotation
    midx : numpy array[np.int_]
        indices where added mass should be applied.
    m : numpy array[nMass], [kg]
        added mass
    mIxx : numpy array[nMass], [kg*m**2]
        x mass moment of inertia about some point p
    mIyy : numpy array[nMass], [kg*m**2]
        y mass moment of inertia about some point p
    mIzz : numpy array[nMass], [kg*m**2]
        z mass moment of inertia about some point p
    mIxy : numpy array[nMass], [kg*m**2]
        xy mass moment of inertia about some point p
    mIxz : numpy array[nMass], [kg*m**2]
        xz mass moment of inertia about some point p
    mIyz : numpy array[nMass], [kg*m**2]
        yz mass moment of inertia about some point p
    mrhox : numpy array[nMass], [m]
        x-location of p relative to node
    mrhoy : numpy array[nMass], [m]
        y-location of p relative to node
    mrhoz : numpy array[nMass], [m]
        z-location of p relative to node
    plidx : numpy array[np.int_]
        indices where point loads should be applied.
    Fx : numpy array[nPL], [N]
        point force in x-direction
    Fy : numpy array[nPL], [N]
        point force in y-direction
    Fz : numpy array[nPL], [N]
        point force in z-direction
    Mxx : numpy array[nPL], [N*m]
        point moment about x-axis
    Myy : numpy array[nPL], [N*m]
        point moment about y-axis
    Mzz : numpy array[nPL], [N*m]
        point moment about z-axis

    """

    def initialize(self):
        self.options.declare("n_height")
        self.options.declare("monopile", default=False)
        self.options.declare("soil_springs", default=False)
        self.options.declare("gravity_foundation", default=False)

    def setup(self):
        n_height = self.options["n_height"]
        nFull = get_nfull(n_height)

        self.add_input("z_full", np.zeros(nFull), units="m")

        # extra mass
        self.add_input("mass", 0.0, units="kg")
        self.add_input("mI", np.zeros(6), units="kg*m**2")
        self.add_input("mrho", np.zeros(3), units="m")
        self.add_input("transition_piece_mass", 0.0, units="kg")
        self.add_input("transition_piece_I", np.zeros(6), units="kg*m**2")
        self.add_input("gravity_foundation_I", np.zeros(6), units="kg*m**2")
        self.add_input("gravity_foundation_mass", 0.0, units="kg")
        self.add_input("transition_piece_height", 0.0, units="m")
        self.add_input("suctionpile_depth", 0.0, units="m")

        # point loads
        self.add_input("rna_F", np.zeros(3), units="N")
        self.add_input("rna_M", np.zeros(3), units="N*m")

        # Monopile handling
        self.add_input("z_soil", np.zeros(NPTS_SOIL), units="N/m")
        self.add_input("k_soil", np.zeros((NPTS_SOIL, 6)), units="N/m")

        # spring reaction data.
        nK = 4 if self.options["monopile"] and not self.options["gravity_foundation"] else 1
        self.add_output("kidx", np.zeros(nK, dtype=np.int_))
        self.add_output("kx", np.zeros(nK), units="N/m")
        self.add_output("ky", np.zeros(nK), units="N/m")
        self.add_output("kz", np.zeros(nK), units="N/m")
        self.add_output("ktx", np.zeros(nK), units="N/m")
        self.add_output("kty", np.zeros(nK), units="N/m")
        self.add_output("ktz", np.zeros(nK), units="N/m")

        # extra mass
        nMass = 3
        self.add_output("midx", np.zeros(nMass, dtype=np.int_))
        self.add_output("m", np.zeros(nMass), units="kg")
        self.add_output("mIxx", np.zeros(nMass), units="kg*m**2")
        self.add_output("mIyy", np.zeros(nMass), units="kg*m**2")
        self.add_output("mIzz", np.zeros(nMass), units="kg*m**2")
        self.add_output("mIxy", np.zeros(nMass), units="kg*m**2")
        self.add_output("mIxz", np.zeros(nMass), units="kg*m**2")
        self.add_output("mIyz", np.zeros(nMass), units="kg*m**2")
        self.add_output("mrhox", np.zeros(nMass), units="m")
        self.add_output("mrhoy", np.zeros(nMass), units="m")
        self.add_output("mrhoz", np.zeros(nMass), units="m")

        # point loads (if addGravityLoadForExtraMass=True be sure not to double count by adding those force here also)
        nPL = 1
        self.add_output("plidx", np.zeros(nPL, dtype=np.int_))
        self.add_output("Fx", np.zeros(nPL), units="N")
        self.add_output("Fy", np.zeros(nPL), units="N")
        self.add_output("Fz", np.zeros(nPL), units="N")
        self.add_output("Mxx", np.zeros(nPL), units="N*m")
        self.add_output("Myy", np.zeros(nPL), units="N*m")
        self.add_output("Mzz", np.zeros(nPL), units="N*m")

        self.declare_partials("Fx", ["rna_F"], method="fd")
        self.declare_partials("Fy", ["rna_F"], method="fd")
        self.declare_partials("Fz", ["rna_F"], method="fd")
        self.declare_partials("G_full", [], method="fd")
        self.declare_partials("Mxx", ["rna_M"], method="fd")
        self.declare_partials("Myy", ["rna_M"], method="fd")
        self.declare_partials("Mzz", ["rna_M"], method="fd")
        self.declare_partials("kidx", [], method="fd")
        self.declare_partials("ktx", [], method="fd")
        self.declare_partials("kty", [], method="fd")
        self.declare_partials("ktz", [], method="fd")
        self.declare_partials("kx", [], method="fd")
        self.declare_partials("ky", [], method="fd")
        self.declare_partials("kz", [], method="fd")
        self.declare_partials("m", ["gravity_foundation_mass", "mass", "transition_piece_mass"], method="fd")
        self.declare_partials("mIxx", ["gravity_foundation_mass", "mI", "transition_piece_mass"], method="fd")
        self.declare_partials("mIxy", ["mI"], method="fd")
        self.declare_partials("mIxz", ["mI"], method="fd")
        self.declare_partials("mIyy", ["gravity_foundation_mass", "mI", "transition_piece_mass"], method="fd")
        self.declare_partials("mIyz", ["mI"], method="fd")
        self.declare_partials("mIzz", ["gravity_foundation_mass", "mI", "transition_piece_mass"], method="fd")
        self.declare_partials("midx", [], method="fd")
        self.declare_partials("mrhox", ["mrho"], method="fd")
        self.declare_partials("mrhoy", ["mrho"], method="fd")
        self.declare_partials("mrhoz", ["mrho"], method="fd")
        self.declare_partials("plidx", [], method="fd")

    def compute(self, inputs, outputs):
        n_height = self.options["n_height"]
        nFull = get_nfull(n_height)
        z = inputs["z_full"]

        # Prepare RNA, transition piece, and gravity foundation (if any applicable) for "extra node mass"
        itrans = util.find_nearest(z, inputs["transition_piece_height"])
        mtrans = inputs["transition_piece_mass"]
        Itrans = inputs["transition_piece_I"]
        mgrav = inputs["gravity_foundation_mass"]
        Igrav = inputs["gravity_foundation_I"]
        # Note, need len()-1 because Frame3DD crashes if mass add at end
        outputs["midx"] = np.array([nFull - 1, itrans, 0], dtype=np.int_)
        outputs["m"] = np.array([inputs["mass"], mtrans, mgrav]).flatten()
        outputs["mIxx"] = np.array([inputs["mI"][0], Itrans[0], Igrav[0]]).flatten()
        outputs["mIyy"] = np.array([inputs["mI"][1], Itrans[1], Igrav[1]]).flatten()
        outputs["mIzz"] = np.array([inputs["mI"][2], Itrans[2], Igrav[2]]).flatten()
        outputs["mIxy"] = np.array([inputs["mI"][3], Itrans[3], Igrav[3]]).flatten()
        outputs["mIxz"] = np.array([inputs["mI"][4], Itrans[4], Igrav[4]]).flatten()
        outputs["mIyz"] = np.array([inputs["mI"][5], Itrans[5], Igrav[5]]).flatten()
        outputs["mrhox"] = np.array([inputs["mrho"][0], 0.0, 0.0]).flatten()
        outputs["mrhoy"] = np.array([inputs["mrho"][1], 0.0, 0.0]).flatten()
        outputs["mrhoz"] = np.array([inputs["mrho"][2], 0.0, 0.0]).flatten()

        # Prepare point forces at RNA node
        outputs["plidx"] = np.array([nFull - 1], dtype=np.int_)  # -1 b/c same reason as above
        outputs["Fx"] = np.array([inputs["rna_F"][0]]).flatten()
        outputs["Fy"] = np.array([inputs["rna_F"][1]]).flatten()
        outputs["Fz"] = np.array([inputs["rna_F"][2]]).flatten()
        outputs["Mxx"] = np.array([inputs["rna_M"][0]]).flatten()
        outputs["Myy"] = np.array([inputs["rna_M"][1]]).flatten()
        outputs["Mzz"] = np.array([inputs["rna_M"][2]]).flatten()

        # Prepare for reactions: rigid at tower base
        if self.options["monopile"] and not self.options["gravity_foundation"]:
            if self.options["soil_springs"]:
                z_soil = inputs["z_soil"]
                k_soil = inputs["k_soil"]
                z_pile = z[z <= (z[0] + 1e-1 + np.abs(z_soil[0]))]
                if z_pile.size != 4:
                    print(z)
                    print(z_soil)
                    print(z_pile)
                    raise ValueError("Please use only one section for submerged pile for now")
                k_mono = np.zeros((z_pile.size, 6))
                for k in range(6):
                    k_mono[:, k] = np.interp(z_pile + np.abs(z_soil[0]), z_soil, k_soil[:, k])
                outputs["kidx"] = np.arange(len(z_pile), dtype=np.int_)
                outputs["kx"] = np.array([k_mono[:, 0]])
                outputs["ky"] = np.array([k_mono[:, 2]])
                outputs["kz"] = np.zeros(k_mono.shape[0])
                outputs["kz"][0] = np.array([k_mono[0, 4]])
                outputs["ktx"] = np.array([k_mono[:, 1]])
                outputs["kty"] = np.array([k_mono[:, 3]])
                outputs["ktz"] = np.array([k_mono[:, 5]])

            else:
                z_pile = z[z <= (z[0] + 1e-1 + inputs["suctionpile_depth"])]
                npile = z_pile.size
                if npile != 4:
                    print(z)
                    print(z_pile)
                    print(inputs["suctionpile_depth"])
                    raise ValueError("Please use only one section for submerged pile for now")
                outputs["kidx"] = np.arange(npile, dtype=np.int_)
                outputs["kx"] = outputs["ky"] = outputs["kz"] = RIGID * np.ones(npile)
                outputs["ktx"] = outputs["kty"] = outputs["ktz"] = RIGID * np.ones(npile)

        else:
            outputs["kidx"] = np.array([0], dtype=np.int_)
            outputs["kx"] = outputs["ky"] = outputs["kz"] = np.array([RIGID])
            outputs["ktx"] = outputs["kty"] = outputs["ktz"] = np.array([RIGID])


class CylinderFrame3DD(om.ExplicitComponent):
    """
    Run Frame3DD on the cylinder geometry

    Parameters
    ----------
    z : numpy array[npts], [m]
        location along cylinder. start at bottom and go to top
    Az : numpy array[npts-1], [m**2]
        cross-sectional area
    Asx : numpy array[npts-1], [m**2]
        x shear area
    Asy : numpy array[npts-1], [m**2]
        y shear area
    Jz : numpy array[npts-1], [m**4]
        polar moment of inertia
    Ixx : numpy array[npts-1], [m**4]
        area moment of inertia about x-axis
    Iyy : numpy array[npts-1], [m**4]
        area moment of inertia about y-axis
    E : numpy array[npts-1], [N/m**2]
        modulus of elasticity
    G : numpy array[npts-1], [N/m**2]
        shear modulus
    rho : numpy array[npts-1], [kg/m**3]
        material density
    d : numpy array[npts], [m]
        effective cylinder diameter for section
    t : numpy array[npts-1], [m]
        effective shell thickness for section
    kidx : numpy array[nK, dtype]
        indices of z where external stiffness reactions should be applied.
    kx : numpy array[nK], [N/m]
        spring stiffness in x-direction
    ky : numpy array[nK], [N/m]
        spring stiffness in y-direction
    kz : numpy array[nK], [N/m]
        spring stiffness in z-direction
    ktx : numpy array[nK], [N/m]
        spring stiffness in theta_x-rotation
    kty : numpy array[nK], [N/m]
        spring stiffness in theta_y-rotation
    ktz : numpy array[nK], [N/m]
        spring stiffness in theta_z-rotation
    midx : numpy array[nMass, dtype]
        indices where added mass should be applied.
    m : numpy array[nMass], [kg]
        added mass
    mIxx : numpy array[nMass], [kg*m**2]
        x mass moment of inertia about some point p
    mIyy : numpy array[nMass], [kg*m**2]
        y mass moment of inertia about some point p
    mIzz : numpy array[nMass], [kg*m**2]
        z mass moment of inertia about some point p
    mIxy : numpy array[nMass], [kg*m**2]
        xy mass moment of inertia about some point p
    mIxz : numpy array[nMass], [kg*m**2]
        xz mass moment of inertia about some point p
    mIyz : numpy array[nMass], [kg*m**2]
        yz mass moment of inertia about some point p
    mrhox : numpy array[nMass], [m]
        x-location of p relative to node
    mrhoy : numpy array[nMass], [m]
        y-location of p relative to node
    mrhoz : numpy array[nMass], [m]
        z-location of p relative to node
    plidx : numpy array[nPL, dtype]
        indices where point loads should be applied.
    Fx : numpy array[nPL], [N]
        point force in x-direction
    Fy : numpy array[nPL], [N]
        point force in y-direction
    Fz : numpy array[nPL], [N]
        point force in z-direction
    Mxx : numpy array[nPL], [N*m]
        point moment about x-axis
    Myy : numpy array[nPL], [N*m]
        point moment about y-axis
    Mzz : numpy array[nPL], [N*m]
        point moment about z-axis
    Px : numpy array[npts], [N/m]
        force per unit length in x-direction
    Py : numpy array[npts], [N/m]
        force per unit length in y-direction
    Pz : numpy array[npts], [N/m]
        force per unit length in z-direction
    qdyn : numpy array[npts], [N/m**2]
        dynamic pressure

    Returns
    -------
    mass : float, [kg]
        Structural mass computed by Frame3DD
    f1 : float, [Hz]
        First natural frequency
    f2 : float, [Hz]
        Second natural frequency
    freqs : numpy array[NFREQ], [Hz]
        Natural frequencies of the structure
    x_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the x-direction
    y_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the y-direction
    z_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the z-direction
    x_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the x-direction
    y_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the y-direction
    z_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the z-direction
    cylinder_deflection : numpy array[npts], [m]
        Deflection of cylinder nodes in yaw-aligned +x direction
    Fz_out : numpy array[npts-1], [N]
        Axial foce in vertical z-direction in cylinder structure.
    Vx_out : numpy array[npts-1], [N]
        Shear force in x-direction in cylinder structure.
    Vy_out : numpy array[npts-1], [N]
        Shear force in y-direction in cylinder structure.
    Mxx_out : numpy array[npts-1], [N*m]
        Moment about x-axis in cylinder structure.
    Myy_out : numpy array[npts-1], [N*m]
        Moment about y-axis in cylinder structure.
    Mzz_out : numpy array[npts-1], [N*m]
        Moment about z-axis in cylinder structure.
    base_F : numpy array[3], [N]
        Total force on cylinder
    base_M : numpy array[3], [N*m]
        Total moment on cylinder measured at base
    axial_stress : numpy array[npts-1], [N/m**2]
        Axial stress in cylinder structure
    shear_stress : numpy array[npts-1], [N/m**2]
        Shear stress in cylinder structure
    hoop_stress : numpy array[npts-1], [N/m**2]
        Hoop stress in cylinder structure calculated with simple method used in API
        standards
    hoop_stress_euro : numpy array[npts-1], [N/m**2]
        Hoop stress in cylinder structure calculated with Eurocode method

    """

    def initialize(self):
        self.options.declare("npts")
        self.options.declare("nK")
        self.options.declare("nMass")
        self.options.declare("nPL")
        self.options.declare("frame3dd_opt")

    def setup(self):
        npts = self.options["npts"]
        nK = self.options["nK"]
        nMass = self.options["nMass"]
        nPL = self.options["nPL"]

        # cross-sectional data along cylinder.
        self.add_input("z", val=np.zeros(npts), units="m")
        self.add_input("Az", val=np.zeros(npts - 1), units="m**2")
        self.add_input("Asx", val=np.zeros(npts - 1), units="m**2")
        self.add_input("Asy", val=np.zeros(npts - 1), units="m**2")
        self.add_input("Jz", val=np.zeros(npts - 1), units="m**4")
        self.add_input("Ixx", val=np.zeros(npts - 1), units="m**4")
        self.add_input("Iyy", val=np.zeros(npts - 1), units="m**4")
        self.add_input("E", val=np.zeros(npts - 1), units="N/m**2")
        self.add_input("G", val=np.zeros(npts - 1), units="N/m**2")
        self.add_input("rho", val=np.zeros(npts - 1), units="kg/m**3")

        # effective geometry -- used for handbook methods to estimate hoop stress, buckling, fatigue
        self.add_input("d", val=np.zeros(npts), units="m")
        self.add_input("t", val=np.zeros(npts - 1), units="m")

        # spring reaction data.  Use global RIGID for rigid constraints.
        # JPJ: this next output should be a discrete output
        self.add_input("kidx", val=np.zeros(nK, dtype=np.int_))
        self.add_input("kx", val=np.zeros(nK), units="N/m")
        self.add_input("ky", val=np.zeros(nK), units="N/m")
        self.add_input("kz", val=np.zeros(nK), units="N/m")
        self.add_input("ktx", val=np.zeros(nK), units="N/m")
        self.add_input("kty", val=np.zeros(nK), units="N/m")
        self.add_input("ktz", val=np.zeros(nK), units="N/m")

        # extra mass
        # JPJ: this next output should be a discrete output
        self.add_input("midx", val=np.zeros(nMass, dtype=np.int_))
        self.add_input("m", val=np.zeros(nMass), units="kg")
        self.add_input("mIxx", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mIyy", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mIzz", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mIxy", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mIxz", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mIyz", val=np.zeros(nMass), units="kg*m**2")
        self.add_input("mrhox", val=np.zeros(nMass), units="m")
        self.add_input("mrhoy", val=np.zeros(nMass), units="m")
        self.add_input("mrhoz", val=np.zeros(nMass), units="m")

        # point loads (if addGravityLoadForExtraMass=True be sure not to double count by adding those force here also)
        self.add_input("plidx", val=np.zeros(nPL, dtype=np.int_))
        self.add_input("Fx", val=np.zeros(nPL), units="N")
        self.add_input("Fy", val=np.zeros(nPL), units="N")
        self.add_input("Fz", val=np.zeros(nPL), units="N")
        self.add_input("Mxx", val=np.zeros(nPL), units="N*m")
        self.add_input("Myy", val=np.zeros(nPL), units="N*m")
        self.add_input("Mzz", val=np.zeros(nPL), units="N*m")

        # combined wind-water distributed loads
        self.add_input("Px", val=np.zeros(npts), units="N/m")
        self.add_input("Py", val=np.zeros(npts), units="N/m")
        self.add_input("Pz", val=np.zeros(npts), units="N/m")
        self.add_input("qdyn", val=np.zeros(npts), units="N/m**2")

        NFREQ2 = int(NFREQ / 2)
        self.add_output("mass", val=0.0, units="kg")
        self.add_output("f1", val=0.0, units="Hz")
        self.add_output("f2", val=0.0, units="Hz")
        self.add_output("freqs", val=np.zeros(NFREQ), units="Hz")
        self.add_output("x_mode_shapes", val=np.zeros((NFREQ2, 5)))
        self.add_output("y_mode_shapes", val=np.zeros((NFREQ2, 5)))
        self.add_output("z_mode_shapes", val=np.zeros((NFREQ2, 5)))
        self.add_output("x_mode_freqs", val=np.zeros(NFREQ2), units="Hz")
        self.add_output("y_mode_freqs", val=np.zeros(NFREQ2), units="Hz")
        self.add_output("z_mode_freqs", val=np.zeros(NFREQ2), units="Hz")
        self.add_output("cylinder_deflection", val=np.zeros(npts), units="m")
        self.add_output("Fz_out", val=np.zeros(npts - 1), units="N")
        self.add_output("Vx_out", val=np.zeros(npts - 1), units="N")
        self.add_output("Vy_out", val=np.zeros(npts - 1), units="N")
        self.add_output("Mxx_out", val=np.zeros(npts - 1), units="N*m")
        self.add_output("Myy_out", val=np.zeros(npts - 1), units="N*m")
        self.add_output("Mzz_out", val=np.zeros(npts - 1), units="N*m")
        self.add_output("base_F", val=np.zeros(3), units="N")
        self.add_output("base_M", val=np.zeros(3), units="N*m")
        self.add_output("axial_stress", val=np.zeros(npts - 1), units="N/m**2")
        self.add_output("shear_stress", val=np.zeros(npts - 1), units="N/m**2")
        self.add_output("hoop_stress", val=np.zeros(npts - 1), units="N/m**2")

        # self.declare_partials('*', '*', method='fd', form='central', step=1e-6)

    def compute(self, inputs, outputs):

        frame3dd_opt = self.options["frame3dd_opt"]

        # ------- node data ----------------
        z = inputs["z"]
        n = len(z)
        node = np.arange(1, n + 1)
        x = np.zeros(n)
        y = np.zeros(n)
        r = np.zeros(n)

        nodes = pyframe3dd.NodeData(node, x, y, z, r)
        # -----------------------------------

        # ------ reaction data ------------

        # rigid base
        node = inputs["kidx"] + np.ones(len(inputs["kidx"]))  # add one because 0-based index but 1-based node numbering
        rigid = RIGID

        reactions = pyframe3dd.ReactionData(
            node, inputs["kx"], inputs["ky"], inputs["kz"], inputs["ktx"], inputs["kty"], inputs["ktz"], rigid
        )
        # -----------------------------------

        # ------ frame element data ------------
        element = np.arange(1, n)
        N1 = np.arange(1, n)
        N2 = np.arange(2, n + 1)

        roll = np.zeros(n - 1)

        # average across element b.c. frame3dd uses constant section elements
        # TODO: Use nodal2sectional
        Az = inputs["Az"]
        Asx = inputs["Asx"]
        Asy = inputs["Asy"]
        Jz = inputs["Jz"]
        Ixx = inputs["Ixx"]
        Iyy = inputs["Iyy"]
        E = inputs["E"]
        G = inputs["G"]
        rho = inputs["rho"]

        elements = pyframe3dd.ElementData(element, N1, N2, Az, Asx, Asy, Jz, Ixx, Iyy, E, G, roll, rho)
        # -----------------------------------

        # ------ options ------------
        dx = -1.0
        options = pyframe3dd.Options(frame3dd_opt["shear"], frame3dd_opt["geom"], dx)
        # -----------------------------------

        # initialize frame3dd object
        cylinder = pyframe3dd.Frame(nodes, reactions, elements, options)

        # ------ add extra mass ------------

        # extra node inertia data
        N = inputs["midx"] + np.ones(len(inputs["midx"]))

        add_gravity = True
        cylinder.changeExtraNodeMass(
            N,
            inputs["m"],
            inputs["mIxx"],
            inputs["mIyy"],
            inputs["mIzz"],
            inputs["mIxy"],
            inputs["mIxz"],
            inputs["mIyz"],
            inputs["mrhox"],
            inputs["mrhoy"],
            inputs["mrhoz"],
            add_gravity,
        )

        # ------------------------------------

        # ------- enable dynamic analysis ----------
        Mmethod = 1
        lump = 0
        shift = 0.0
        # Run twice the number of modes to ensure that we can ignore the torsional modes and still get the desired number of fore-aft, side-side modes
        cylinder.enableDynamics(2 * NFREQ, Mmethod, lump, frame3dd_opt["tol"], shift)
        # ----------------------------

        # ------ static load case 1 ------------

        # gravity in the X, Y, Z, directions (global)
        gx = 0.0
        gy = 0.0
        gz = -gravity

        load = pyframe3dd.StaticLoadCase(gx, gy, gz)

        # point loads
        nF = inputs["plidx"] + np.ones(len(inputs["plidx"]))
        load.changePointLoads(nF, inputs["Fx"], inputs["Fy"], inputs["Fz"], inputs["Mxx"], inputs["Myy"], inputs["Mzz"])

        # distributed loads
        Px, Py, Pz = inputs["Pz"], inputs["Py"], -inputs["Px"]  # switch to local c.s.
        z = inputs["z"]

        # trapezoidally distributed loads
        EL = np.arange(1, n)
        xx1 = xy1 = xz1 = np.zeros(n - 1)
        xx2 = xy2 = xz2 = np.diff(z) - 1e-6  # subtract small number b.c. of precision
        wx1 = Px[:-1]
        wx2 = Px[1:]
        wy1 = Py[:-1]
        wy2 = Py[1:]
        wz1 = Pz[:-1]
        wz2 = Pz[1:]

        load.changeTrapezoidalLoads(EL, xx1, xx2, wx1, wx2, xy1, xy2, wy1, wy2, xz1, xz2, wz1, wz2)

        cylinder.addLoadCase(load)
        # Debugging
        # cylinder.write('temp.3dd')
        # -----------------------------------
        # run the analysis
        displacements, forces, reactions, internalForces, mass, modal = cylinder.run()
        iCase = 0

        # mass
        outputs["mass"] = mass.struct_mass

        # natural frequncies
        outputs["f1"] = modal.freq[0]
        outputs["f2"] = modal.freq[1]
        outputs["freqs"] = modal.freq[:NFREQ]

        # Get all mode shapes in batch
        NFREQ2 = int(NFREQ / 2)
        freq_x, freq_y, freq_z, mshapes_x, mshapes_y, mshapes_z = util.get_xyz_mode_shapes(
            z, modal.freq, modal.xdsp, modal.ydsp, modal.zdsp, modal.xmpf, modal.ympf, modal.zmpf
        )
        outputs["x_mode_freqs"] = freq_x[:NFREQ2]
        outputs["y_mode_freqs"] = freq_y[:NFREQ2]
        outputs["z_mode_freqs"] = freq_z[:NFREQ2]
        outputs["x_mode_shapes"] = mshapes_x[:NFREQ2, :]
        outputs["y_mode_shapes"] = mshapes_y[:NFREQ2, :]
        outputs["z_mode_shapes"] = mshapes_z[:NFREQ2, :]

        # deflections due to loading (from cylinder top and wind/wave loads)
        outputs["cylinder_deflection"] = np.sqrt(
            displacements.dx[iCase, :] ** 2 + displacements.dy[iCase, :] ** 2
        )  # in yaw-aligned direction

        # shear and bending, one per element (convert from local to global c.s.)
        Fz = forces.Nx[iCase, 1::2]
        Vy = forces.Vy[iCase, 1::2]
        Vx = -forces.Vz[iCase, 1::2]

        Mzz = forces.Txx[iCase, 1::2]
        Myy = forces.Myy[iCase, 1::2]
        Mxx = -forces.Mzz[iCase, 1::2]

        # Record total forces and moments
        base_idx = 2 * int(inputs["kidx"].max())
        outputs["base_F"] = (
            -1.0 * np.r_[-forces.Vz[iCase, base_idx], forces.Vy[iCase, base_idx], forces.Nx[iCase, base_idx]]
        )
        outputs["base_M"] = (
            -1.0 * np.r_[-forces.Mzz[iCase, base_idx], forces.Myy[iCase, base_idx], forces.Txx[iCase, base_idx]]
        )

        outputs["Fz_out"] = Fz
        outputs["Vx_out"] = Vx
        outputs["Vy_out"] = Vy
        outputs["Mxx_out"] = Mxx
        outputs["Myy_out"] = Myy
        outputs["Mzz_out"] = Mzz

        # axial and shear stress
        d, _ = util.nodal2sectional(inputs["d"])
        r = 0.5 * d
        qdyn, _ = util.nodal2sectional(inputs["qdyn"])

        ##R = self.d/2.0
        ##x_stress = R*np.cos(self.theta_stress)
        ##y_stress = R*np.sin(self.theta_stress)
        ##axial_stress = Fz/self.Az + Mxx/self.Ixx*y_stress - Myy/Iyy*x_stress
        #        V = Vy*x_stress/R - Vx*y_stress/R  # shear stress orthogonal to direction x,y
        #        shear_stress = 2. * V / self.Az  # coefficient of 2 for a hollow circular section, but should be conservative for other shapes

        # See http://svn.code.sourceforge.net/p/frame3dd/code/trunk/doc/Frame3DD-manual.html#structuralmodeling
        M = np.sqrt(Mxx ** 2 + Myy ** 2)
        V = np.sqrt(Vx ** 2 + Vy ** 2)

        outputs["axial_stress"] = Fz / Az + M * r / Iyy

        outputs["shear_stress"] = np.abs(Mzz) / Jz * r + V / Asx

        # Simpler hoop stress used in API calculations
        outputs["hoop_stress"] = hoopStress(d, inputs["t"], qdyn)


class TowerPostFrame(om.ExplicitComponent):
    """
    Postprocess results from Frame3DD.

    Parameters
    ----------
    z_full : numpy array[nFull], [m]
        location along tower. start at bottom and go to top
    d_full : numpy array[nFull], [m]
        effective tower diameter for section
    t_full : numpy array[nFull-1], [m]
        effective shell thickness for section
    E_full : numpy array[nFull-1], [N/m**2]
        modulus of elasticity
    sigma_y_full : numpy array[nFull-1], [N/m**2]
        yield stress
    Fz : numpy array[nFull-1], [N]
        Axial foce in vertical z-direction in cylinder structure.
    Mxx : numpy array[nFull-1], [N*m]
        Moment about x-axis in cylinder structure.
    Myy : numpy array[nFull-1], [N*m]
        Moment about y-axis in cylinder structure.
    axial_stress : numpy array[nFull-1], [N/m**2]
        axial stress in tower elements
    shear_stress : numpy array[nFull-1], [N/m**2]
        shear stress in tower elements
    hoop_stress : numpy array[nFull-1], [N/m**2]
        hoop stress in tower elements
    tower_deflection_in : numpy array[nFull], [m]
        Deflection of tower nodes in yaw-aligned +x direction
    life : float
        fatigue life of tower
    freqs : numpy array[NFREQ], [Hz]
        Natural frequencies of the structure
    x_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the x-direction
    y_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the y-direction
    z_mode_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the z-direction
    x_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the x-direction
    y_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the y-direction
    z_mode_shapes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the z-direction

    Returns
    -------
    structural_frequencies : numpy array[NFREQ], [Hz]
        First and second natural frequency
    fore_aft_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the tower fore-aft direction
    side_side_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the tower side-side direction
    torsion_freqs : numpy array[NFREQ2]
        Frequencies associated with mode shapes in the tower torsion direction
    fore_aft_modes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the tower fore-aft direction
        (without constant term)
    side_side_modes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the tower side-side direction
        (without constant term)
    torsion_modes : numpy array[NFREQ2, 5]
        6-degree polynomial coefficients of mode shapes in the tower torsion direction
        (without constant term)
    tower_deflection : numpy array[nFull], [m]
        Deflection of tower nodes in yaw-aligned +x direction
    top_deflection : float, [m]
        Deflection of tower top in yaw-aligned +x direction
    stress : numpy array[nFull-1]
        Von Mises stress utilization along tower at specified locations. Includes safety
        factor.
    shell_buckling : numpy array[nFull-1]
        Shell buckling constraint. Should be < 1 for feasibility. Includes safety
        factors
    global_buckling : numpy array[nFull-1]
        Global buckling constraint. Should be < 1 for feasibility. Includes safety
        factors
    turbine_F : numpy array[3], [N]
        Total force on tower+rna
    turbine_M : numpy array[3], [N*m]
        Total x-moment on tower+rna measured at base

    """

    def initialize(self):
        self.options.declare("n_height")
        self.options.declare("modeling_options")
        # self.options.declare('nDEL')

    def setup(self):
        n_height = self.options["n_height"]
        nFull = get_nfull(n_height)

        # effective geometry -- used for handbook methods to estimate hoop stress, buckling, fatigue
        self.add_input("z_full", np.zeros(nFull), units="m")
        self.add_input("d_full", np.zeros(nFull), units="m")
        self.add_input("t_full", np.zeros(nFull - 1), units="m")
        self.add_input("suctionpile_depth", 0.0, units="m")

        # Material properties
        self.add_input("E_full", np.zeros(nFull - 1), units="N/m**2", desc="modulus of elasticity")
        self.add_input(
            "G_full",
            np.zeros(nFull - 1),
            units="Pa",
            desc="Isotropic shear modulus of the materials along the tower sections.",
        )
        self.add_input(
            "rho_full", np.zeros(nFull - 1), units="kg/m**3", desc="Density of the materials along the tower sections."
        )
        self.add_input("sigma_y_full", np.zeros(nFull - 1), units="N/m**2", desc="yield stress")

        # Processed Frame3DD outputs
        self.add_input("Fz", np.zeros(nFull - 1), units="N")
        self.add_input("Mxx", np.zeros(nFull - 1), units="N*m")
        self.add_input("Myy", np.zeros(nFull - 1), units="N*m")
        self.add_input("axial_stress", val=np.zeros(nFull - 1), units="N/m**2")
        self.add_input("shear_stress", val=np.zeros(nFull - 1), units="N/m**2")
        self.add_input("hoop_stress", val=np.zeros(nFull - 1), units="N/m**2")
        self.add_input("tower_deflection_in", val=np.zeros(nFull), units="m")

        # safety factors
        # self.add_input('gamma_f', 1.35, desc='safety factor on loads')
        # self.add_input('gamma_m', 1.1, desc='safety factor on materials')
        # self.add_input('gamma_n', 1.0, desc='safety factor on consequence of failure')
        # self.add_input('gamma_b', 1.1, desc='buckling safety factor')
        # self.add_input('gamma_fatigue', 1.755, desc='total safety factor for fatigue')

        # fatigue parameters
        self.add_input("life", 20.0)
        # self.add_input('m_SN', 4, desc='slope of S/N curve')
        # self.add_input('DC', 80.0, desc='standard value of stress')
        # self.add_input('z_DEL', np.zeros(nDEL), units='m', desc='absolute z coordinates of corresponding fatigue parameters')
        # self.add_input('M_DEL', np.zeros(nDEL), desc='fatigue parameters at corresponding z coordinates')

        # Frequencies
        NFREQ2 = int(NFREQ / 2)

        self.add_input("freqs", val=np.zeros(NFREQ), units="Hz", desc="Natural frequencies of the structure")
        self.add_input(
            "x_mode_shapes",
            val=np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the x-direction (x^2..x^6, no linear or constant term)",
        )
        self.add_input(
            "y_mode_shapes",
            val=np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the y-direction (x^2..x^6, no linear or constant term)",
        )
        self.add_input(
            "z_mode_shapes",
            val=np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the z-direction (x^2..x^6, no linear or constant term)",
        )
        self.add_input(
            "x_mode_freqs",
            val=np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the x-direction",
        )
        self.add_input(
            "y_mode_freqs",
            val=np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the y-direction",
        )
        self.add_input(
            "z_mode_freqs",
            val=np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the z-direction",
        )

        # outputs
        self.add_output(
            "structural_frequencies", np.zeros(NFREQ), units="Hz", desc="First and second natural frequency"
        )
        self.add_output(
            "fore_aft_modes",
            np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the tower fore-aft direction (x^2..x^6, no linear or constant term)",
        )
        self.add_output(
            "side_side_modes",
            np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the tower side-side direction (x^2..x^6, no linear or constant term)",
        )
        self.add_output(
            "torsion_modes",
            np.zeros((NFREQ2, 5)),
            desc="6-degree polynomial coefficients of mode shapes in the tower torsion direction (x^2..x^6, no linear or constant term)",
        )
        self.add_output(
            "fore_aft_freqs",
            np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the tower fore-aft direction",
        )
        self.add_output(
            "side_side_freqs",
            np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the tower side-side direction",
        )
        self.add_output(
            "torsion_freqs",
            np.zeros(NFREQ2),
            units="Hz",
            desc="Frequencies associated with mode shapes in the tower side-side direction",
        )
        self.add_output(
            "tower_deflection", np.zeros(nFull), units="m", desc="Deflection of tower top in yaw-aligned +x direction"
        )
        self.add_output("top_deflection", 0.0, units="m", desc="Deflection of tower top in yaw-aligned +x direction")
        self.add_output("hoop_stress_euro", val=np.zeros(nFull - 1), units="N/m**2")
        self.add_output(
            "stress",
            np.zeros(nFull - 1),
            desc="Von Mises stress utilization along tower at specified locations.  incudes safety factor.",
        )
        self.add_output(
            "shell_buckling",
            np.zeros(nFull - 1),
            desc="Shell buckling constraint.  Should be < 1 for feasibility.  Includes safety factors",
        )
        self.add_output(
            "global_buckling",
            np.zeros(nFull - 1),
            desc="Global buckling constraint.  Should be < 1 for feasibility.  Includes safety factors",
        )
        # self.add_output('damage', np.zeros(nFull-1), desc='Fatigue damage at each tower section')
        self.add_output("turbine_F", val=np.zeros(3), units="N", desc="Total force on tower+rna")
        self.add_output("turbine_M", val=np.zeros(3), units="N*m", desc="Total x-moment on tower+rna measured at base")

        self.declare_partials(
            "global_buckling", ["Fz", "Mxx", "Myy", "d_full", "sigma_y_full", "t_full", "z_full"], method="fd"
        )
        self.declare_partials(
            "shell_buckling",
            ["axial_stress", "d_full", "hoop_stress", "shear_stress", "sigma_y_full", "t_full"],
            method="fd",
        )
        # self.declare_partials("stress", ["axial_stress", "hoop_stress", "shear_stress", "sigma_y_full"], method="fd")
        # self.declare_partials("structural_frequencies", ["freqs"], method="fd")
        # self.declare_partials("fore_aft_freqs", ["x_mode_freqs"], method="fd")
        # self.declare_partials("side_side_freqs", ["y_mode_freqs"], method="fd")
        # self.declare_partials("fore_aft_modes", ["x_mode_shapes"], method="fd")
        # self.declare_partials("side_side_modes", ["y_mode_shapes"], method="fd")
        # self.declare_partials("turbine_F", [], method="fd")
        # self.declare_partials("turbine_M", [], method="fd")

    def compute(self, inputs, outputs):
        # Unpack some variables
        axial_stress = inputs["axial_stress"]
        shear_stress = inputs["shear_stress"]
        hoop_stress = inputs["hoop_stress"]
        sigma_y = inputs["sigma_y_full"]
        E = inputs["E_full"]
        G = inputs["G_full"]
        z = inputs["z_full"]
        t = inputs["t_full"]
        d = inputs["d_full"]
        d_sec, _ = util.nodal2sectional(d)
        z_sec, _ = util.nodal2sectional(z)

        L_suction = float(inputs["suctionpile_depth"])
        L_buckling = self.options["modeling_options"]["buckling_length"] * np.ones(axial_stress.shape)
        gamma_f = self.options["modeling_options"]["gamma_f"]
        gamma_m = self.options["modeling_options"]["gamma_m"]
        gamma_n = self.options["modeling_options"]["gamma_n"]
        gamma_b = self.options["modeling_options"]["gamma_b"]

        # Frequencies and mode shapes (with x^2 term first)
        outputs["structural_frequencies"] = inputs["freqs"]
        outputs["fore_aft_freqs"] = inputs["x_mode_freqs"]
        outputs["side_side_freqs"] = inputs["y_mode_freqs"]
        outputs["torsion_freqs"] = inputs["z_mode_freqs"]
        outputs["fore_aft_modes"] = inputs["x_mode_shapes"]
        outputs["side_side_modes"] = inputs["y_mode_shapes"]
        outputs["torsion_modes"] = inputs["z_mode_shapes"]

        # Tower top deflection
        outputs["tower_deflection"] = inputs["tower_deflection_in"]
        outputs["top_deflection"] = inputs["tower_deflection_in"][-1]

        # von mises stress
        outputs["stress"] = util_con.vonMisesStressUtilization(
            axial_stress, hoop_stress, shear_stress, gamma_f * gamma_m * gamma_n, sigma_y
        )

        # Buckling checks
        M = np.sqrt(inputs["Mxx"] ** 2 + inputs["Myy"] ** 2)
        Fz = inputs["Fz"]

        if self.options["modeling_options"]["buckling_method"].lower().find("euro") >= 0:
            # Use Euro-code method
            hoop_euro = util_euro.hoopStressEurocode(d_sec, t, L_buckling, hoop_stress)
            outputs["hoop_stress_euro"] = hoop_euro

            shell_buckling = util_euro.shellBucklingEurocode(
                d, t, axial_stress, hoop_euro, shear_stress, L_buckling, E, sigma_y, gamma_f, gamma_b
            )

            tower_height = z[-1] - z[0] - L_suction
            global_buckling = util_euro.bucklingGL(d_sec, t, Fz, M, tower_height, E, sigma_y, gamma_f, gamma_b)

        else:
            # Use DNV-GL CP202 Method
            check = util_dnvgl.CylinderBuckling(
                z, d, t, E=E, G=G, sigma_y=sigma_y, gamma=gamma_f * gamma_b, mod_length=L_suction
            )
            results = check.run_buckling_checks(Fz, M, axial_stress, hoop_stress, shear_stress)
            shell_buckling = results["Shell"]
            global_buckling = results["Global"]

        outputs["shell_buckling"] = shell_buckling
        outputs["global_buckling"] = global_buckling

        # fatigue
        # N_DEL = 365.0 * 24.0 * 3600.0 * inputs["life"] * np.ones(len(t))
        # outputs['damage'] = np.zeros(N_DEL.shape)

        # if any(inputs['M_DEL']):
        #    M_DEL = np.interp(z_section, inputs['z_DEL'], inputs['M_DEL'])

        #    outputs['damage'] = util_con.fatigue(M_DEL, N_DEL, d, inputs['t'], inputs['m_SN'],
        #                                      inputs['DC'], gamma_fatigue, stress_factor=1.0, weld_factor=True)

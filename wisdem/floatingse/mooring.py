import numpy as np
import moorpy as mp
import openmdao.api as om

NLINES_MAX = 15
NPTS_PLOT = 21


def set_properties(Dmooring, lineTypeIn):
    """
    THIS IS NOT USED BUT REMAINS FOR REFERENCE
    Sets mooring line properties: Minimum Breaking Load, Mass per Length,
    Axial Stiffness, Cross-Sectional Area, Cost-per-Length.

    INPUTS:
    ----------
    inputs   : dictionary of input parameters

    OUTPUTS  : Parameters are class variables and are set internally

    References:
    https://daim.idi.ntnu.no/masteroppgaver/015/15116/masteroppgave.pdf
    http://offshoremechanics.asmedigitalcollection.asme.org/article.aspx?articleid=2543338
    https://www.orcina.com/SoftwareProducts/OrcaFlex/Documentation/Help/Content/html/
    Chain.htm
    Chain,AxialandBendingStiffness.htm
    Chain,MechanicalProperties.htm
    RopeWire.htm
    RopeWire,MinimumBreakingLoads.htm
    RopeWire,Massperunitlength.htm
    RopeWire,AxialandBendingStiffness.htm
    """

    # Unpack variables
    lineType = lineTypeIn.upper()

    # Set parameters based on regressions for different mooring line type
    Dmooring2 = Dmooring ** 2

    # TODO: Costs per unit length are not synced with new input sources
    if lineType == "CHAIN":
        min_break_load = 2.74e7 * Dmooring2 * (44.0 - 80.0 * Dmooring)
        # Use a linear fit to the other fit becuase it is poorly conditioned for optimization
        # min_break_load      = 1e3*np.maximum(1.0, -5445.2957034820683+176972.68498888266*Dmooring)
        wet_mass_per_length = 19.9e3 * Dmooring2  # From Orca, 7983.34117 OC3 definiton doc
        axial_stiffness = 8.54e10 * Dmooring2  # From Orca, 4.74374e10 OC3 definiton doc,
        area = 2.0 * 0.25 * np.pi * Dmooring2
        cost_per_length = 3.415e4 * Dmooring2  # 0.58*1e-3*min_break_load/gravity - 87.6

    elif lineType == "NYLON":
        min_break_load = 139357e3 * Dmooring2
        wet_mass_per_length = 0.6476e3 * Dmooring2
        axial_stiffness = 1.18e8 * Dmooring2
        area = 0.25 * np.pi * Dmooring2
        cost_per_length = 3.415e4 * Dmooring2  # 0.42059603*1e-3*min_break_load/gravity + 109.5

    elif lineType == "POLYESTER":
        min_break_load = 170466e3 * Dmooring2
        wet_mass_per_length = 0.7978e3 * Dmooring2
        axial_stiffness = 1.09e9 * Dmooring2
        area = 0.25 * np.pi * Dmooring2
        cost_per_length = 3.415e4 * Dmooring2  # 0.42059603*1e-3*min_break_load/gravity + 109.5

    elif lineType == "FIBER":  # Wire rope with fiber rope
        min_break_load = 584175e3 * Dmooring2
        wet_mass_per_length = 3.6109e3 * Dmooring2
        axial_stiffness = 3.67e10 * Dmooring2
        area = 0.455 * 0.25 * np.pi * Dmooring2
        cost_per_length = 2.0 * 6.32e4 * Dmooring2  # 0.53676471*1e-3*min_break_load/gravity

    elif lineType == "IWRC":  # Wire rope with steel core
        min_break_load = 633358e3 * Dmooring2
        wet_mass_per_length = 3.9897e3 * Dmooring2
        axial_stiffness = 4.04e10 * Dmooring2
        area = 0.455 * 0.25 * np.pi * Dmooring2
        cost_per_length = 6.32e4 * Dmooring2  # 0.33*1e-3*min_break_load/gravity + 139.5

    else:
        raise ValueError("Available line types are: chain nylon polyester fiber iwrc")

    return min_break_load, wet_mass_per_length, axial_stiffness, area, cost_per_length


class Mooring(om.ExplicitComponent):
    """
    Sets mooring line properties then writes MAP input file and executes MAP.

    Component for mooring system attached to sub-structure of floating offshore wind turbines.
    Should be tightly coupled with Spar class for full system representation.

    Parameters
    ----------
    water_density : float, [kg/m**3]
        density of water
    water_depth : float, [m]
        water depth
    fairlead_radius : float, [m]
        Mooring attachment distance from vessel centerline
    fairlead : float, [m]
        Depth below water for mooring line attachment
    line_length : float, [m]
        Unstretched total mooring line length
    anchor_radius : float, [m]
        radius from center of spar to mooring anchor point
    line_diameter : float, [m]
        diameter of mooring line
    anchor_type : string
        SUCTIONPILE or DRAGEMBEDMENT
    max_surge_fraction : float
        Maximum allowable surge offset as a fraction of water depth (0-1)
    operational_heel : float, [deg]
        Maximum angle of heel allowable during operation
    survival_heel : float, [deg]
        max heel angle for turbine survival

    Returns
    -------
    line_mass : float, [kg]
        mass of single mooring line
    mooring_mass : float, [kg]
        total mass of mooring
    mooring_cost : float, [USD]
        total cost for anchor + legs + miscellaneous costs
    mooring_stiffness : numpy array[6, 6], [N/m]
        Linearized stiffness matrix of mooring system at neutral (no offset) conditions.
    anchor_cost : float, [USD]
        total cost for anchor
    mooring_neutral_load : numpy array[NLINES_MAX, 3], [N]
        mooring vertical load in all mooring lines
    max_offset_restoring_force : float, [N]
        sum of forces in x direction after max offset
    operational_heel_restoring_force : numpy array[NLINES_MAX, 3], [N]
        forces for all mooring lines after operational heel
    survival_heel_restoring_force : numpy array[NLINES_MAX, 3], [N]
        forces for all mooring lines after max survival heel
    mooring_plot_matrix : numpy array[NLINES_MAX, NPTS_PLOT, 3], [m]
        data matrix for plotting
    constr_axial_load : float, [m]
        range of damaged mooring
    constr_mooring_length : float
        mooring line length ratio to nodal distance

    """

    def initialize(self):
        self.options.declare("options")
        self.options.declare("gamma")

    def setup(self):
        n_lines = self.options["options"]["n_anchors"]
        n_attach = self.options["options"]["n_attach"]

        # Variables local to the class and not OpenMDAO
        self.finput = None
        self.tlpFlag = False

        self.add_input("water_depth", 0.0, units="m")

        # Design variables
        self.add_input("fairlead_radius", 0.0, units="m")
        self.add_input("fairlead", 0.0, units="m")
        self.add_input("line_length", 0.0, units="m")
        self.add_input("line_diameter", 0.0, units="m")
        self.add_input("anchor_radius", 0.0, units="m")
        self.add_input("anchor_cost", 0.0, units="USD")

        self.add_input("line_mass_density_coeff", 0.0, units="kg/m**3")
        self.add_input("line_stiffness_coeff", 0.0, units="N/m**2")
        self.add_input("line_breaking_load_coeff", 0.0, units="N/m**2")
        self.add_input("line_cost_rate_coeff", 0.0, units="USD/m**3")

        # User inputs (could be design variables)
        # self.add_discrete_input("mooring_type", "CHAIN")
        # self.add_discrete_input("anchor_type", "DRAGEMBEDMENT")
        self.add_input("max_surge_fraction", 0.1)
        self.add_input("operational_heel", 0.0, units="rad")
        self.add_input("survival_heel", 0.0, units="rad")

        self.add_output("line_mass", 0.0, units="kg")
        self.add_output("mooring_mass", 0.0, units="kg")
        self.add_output("mooring_cost", 0.0, units="USD")
        self.add_output("mooring_stiffness", np.zeros((6, 6)), units="N/m")
        self.add_output("mooring_neutral_load", np.zeros((n_attach, 3)), units="N")
        self.add_output("max_surge_restoring_force", 0.0, units="N")
        self.add_output("operational_heel_restoring_force", np.zeros(6), units="N")
        self.add_output("survival_heel_restoring_force", np.zeros(6), units="N")
        self.add_output("mooring_plot_matrix", np.zeros((n_lines, NPTS_PLOT, 3)), units="m")

        # Constraints
        self.add_output("constr_axial_load", 0.0, units="m")
        self.add_output("constr_mooring_length", 0.0)

    def compute(self, inputs, outputs):
        # Set characteristics based on regressions / empirical data
        # self.set_properties(inputs, discrete_inputs)

        # Set geometry profile
        self.geometry_constraints(inputs, outputs)

        # Write MAP input file and analyze the system at every angle
        self.evaluate_mooring(inputs, outputs)

        # Compute costs for the system
        self.compute_cost(inputs, outputs)

    def geometry_constraints(self, inputs, outputs):
        # Unpack variables
        fairleadDepth = inputs["fairlead"]
        R_fairlead = inputs["fairlead_radius"]
        R_anchor = inputs["anchor_radius"]
        waterDepth = inputs["water_depth"]
        L_mooring = inputs["line_length"]
        max_heel = inputs["survival_heel"]
        gamma = self.options["gamma"]

        if L_mooring > (waterDepth - fairleadDepth):
            self.tlpFlag = False

            # Create constraint that line isn't too long that there is no catenary hang
            outputs["constr_mooring_length"] = L_mooring / (0.95 * (R_anchor + waterDepth - fairleadDepth))
        else:
            self.tlpFlag = True
            # Create constraint that we don't lose line tension
            outputs["constr_mooring_length"] = L_mooring / (
                (waterDepth - fairleadDepth - gamma * R_fairlead * np.sin(max_heel))
            )

    def evaluate_mooring(self, inputs, outputs):
        """Writes MAP input file, executes, and then queries MAP to find
        maximum loading and displacement from vessel displacement around all 360 degrees

        INPUTS:
        ----------
        inputs   : dictionary of input parameters
        outputs : dictionary of output parameters

        OUTPUTS  : none (multiple unknown dictionary values set)
        """
        # Unpack variables
        water_depth = float(inputs["water_depth"])
        fairlead_depth = float(inputs["fairlead"])
        R_fairlead = float(inputs["fairlead_radius"])
        R_anchor = float(inputs["anchor_radius"])
        heel = float(inputs["operational_heel"])
        max_heel = inputs["survival_heel"]
        d = inputs["line_diameter"]
        L_mooring = inputs["line_length"]
        min_break_load = inputs["line_breaking_load_coeff"] * d ** 2
        gamma = self.options["gamma"]
        n_attach = self.options["options"]["n_attach"]
        n_lines = self.options["options"]["n_anchors"]
        offset = float(inputs["max_surge_fraction"]) * water_depth
        n_anchors = self.options["options"]["n_anchors"]
        ratio = int(n_anchors / n_attach)

        # Create input dictionary
        config = {}
        config["water_depth"] = water_depth

        config["points"] = [dict() for k in range(n_attach + n_anchors)]
        angles = np.linspace(0, 2 * np.pi, n_attach + 1)[:n_attach]
        angles -= np.mean(angles)
        fair_x = R_fairlead * np.cos(angles)
        fair_y = R_fairlead * np.sin(angles)
        angles = np.linspace(0, 2 * np.pi, n_anchors + 1)[:n_anchors]
        angles -= np.mean(angles)
        anchor_x = R_anchor * np.cos(angles)
        anchor_y = R_anchor * np.sin(angles)
        for k in range(n_attach):
            config["points"][k]["name"] = f"fairlead{k}"
            config["points"][k]["type"] = "vessel"
            config["points"][k]["location"] = [fair_x[k], fair_y[k], -fairlead_depth]
        for k in range(n_anchors):
            config["points"][k + n_attach]["name"] = f"anchor{k}"
            config["points"][k + n_attach]["type"] = "fixed"
            config["points"][k + n_attach]["location"] = [anchor_x[k], anchor_y[k], -water_depth]

        config["lines"] = [dict() for i in range(n_lines)]
        for k in range(n_lines):
            ifair = np.int_(k / ratio)
            config["lines"][k]["name"] = f"line{k}"
            config["lines"][k]["endA"] = f"fairlead{ifair}"
            config["lines"][k]["endB"] = f"anchor{k}"
            config["lines"][k]["type"] = "myline"
            config["lines"][k]["length"] = L_mooring

        config["line_types"] = [{}]
        config["line_types"][0]["name"] = "myline"
        config["line_types"][0]["diameter"] = d
        config["line_types"][0]["mass_density"] = inputs["line_mass_density_coeff"] * d ** 2
        config["line_types"][0]["stiffness"] = inputs["line_stiffness_coeff"] * d ** 2
        config["line_types"][0]["breaking_load"] = inputs["line_breaking_load_coeff"] * d ** 2
        config["line_types"][0]["cost"] = inputs["line_cost_rate_coeff"] * d ** 2
        config["line_types"][0]["transverse_added_mass"] = 0.0
        config["line_types"][0]["tangential_added_mass"] = 0.0
        config["line_types"][0]["transverse_drag"] = 0.0
        config["line_types"][0]["tangential_drag"] = 0.0

        # Create a MoorPy system
        ms = mp.System()
        ms.parseYAML(config)
        ms.BodyList[0].type = -1  # need to make sure it's set to a coupled type
        ms.initialize()

        # Get the stiffness matrix at neutral position
        ms.BodyList[0].setPosition(np.zeros(6))
        ms.solveEquilibrium3()
        outputs["mooring_stiffness"] = ms.getCoupledStiffness(lines_only=True)

        # Get the vertical load in the neutral position
        F_neut = ms.getForces(DOFtype="coupled", lines_only=True)
        outputs["mooring_neutral_load"] = np.outer(np.ones(n_attach), F_neut[:3] / n_attach)

        # Plotting data
        plotMat = np.zeros((n_lines, NPTS_PLOT, 3))
        for k in range(n_lines):
            Xs, Ys, Zs = ms.LineList[k].GetLineCoords(0.0)
            plotMat[k, :, 0] = Xs
            plotMat[k, :, 1] = Ys
            plotMat[k, :, 2] = Zs
        outputs["mooring_plot_matrix"] = plotMat

        # Get the restoring moment at maximum angle of heel
        # Since we don't know the substucture CG, have to just get the forces of the lines now and do the cross product later
        # We also want to allow for arbitraty wind direction and yaw of rotor relative to mooring lines, so we will compare
        # pitch and roll forces as extremes
        F_heel = ms.mooringEq([0, 0, 0, 0, heel, 0], DOFtype="coupled")
        outputs["operational_heel_restoring_force"] = F_heel

        F_maxheel = ms.mooringEq([0, 0, 0, 0, max_heel, 0], DOFtype="coupled")
        outputs["survival_heel_restoring_force"] = F_maxheel

        # TODO: Vertical loads on anchors?

        # Get angles by which to find the weakest line
        dangle = 5.0
        angles = np.deg2rad(np.arange(0.0, 360.0, dangle))
        nangles = angles.size

        # Get restoring force at weakest line at maximum allowable offset
        # Will global minimum always be along mooring angle?
        Frestore = np.zeros(nangles)
        Tmax = np.zeros(nangles)
        Fa = np.zeros(n_lines)
        # Loop around all angles to find weakest point
        for ia, a in enumerate(angles):
            # Unit vector and offset in x-y components
            idir = np.array([np.cos(a), np.sin(a)])
            surge = offset * idir[0]
            sway = offset * idir[1]

            # Get restoring force of offset at this angle
            fbody = ms.mooringEq([surge, sway, 0, 0, 0, 0], DOFtype="coupled")
            Frestore[ia] = np.dot(fbody[:2], idir)
            for k in range(n_lines):
                f = ms.LineList[0].getEndForce(endB=0)
                Fa[k] = np.sqrt(np.sum(f ** 2))

            Tmax[ia] = np.abs(Fa).max()

        # Store the weakest restoring force when the vessel is offset the maximum amount
        outputs["max_surge_restoring_force"] = np.abs(Frestore).min()

        # Check for good convergence
        outputs["constr_axial_load"] = gamma * Tmax.max() / min_break_load

    def compute_cost(self, inputs, outputs):
        """Computes cost, based on mass scaling, of mooring system.

        INPUTS:
        ----------
        inputs   : dictionary of input parameters
        outputs : dictionary of output parameters

        OUTPUTS  : none (mooring_cost/mass unknown dictionary values set)
        """
        # Unpack variables
        L_mooring = float(inputs["line_length"])
        # anchorType = discrete_inputs["anchor_type"]
        d = float(inputs["line_diameter"])
        cost_per_length = float(inputs["line_cost_rate_coeff"]) * d ** 2
        # min_break_load = inputs['line_breaking_load_coeff'] * d**2
        wet_mass_per_length = float(inputs["line_mass_density_coeff"]) * d ** 2
        anchor_rate = float(inputs["anchor_cost"])
        n_anchors = n_lines = self.options["options"]["n_anchors"]

        # Cost of anchors
        # if anchorType.upper() == "DRAGEMBEDMENT":
        #    anchor_rate = 1e-3 * min_break_load / gravity / 20 * 2000
        # elif anchorType.upper() == "SUCTIONPILE":
        #    anchor_rate = 150000.0 * np.sqrt(1e-3 * min_break_load / gravity / 1250.0)
        # else:
        #    raise ValueError("Anchor Type must be DRAGEMBEDMENT or SUCTIONPILE")
        anchor_total = anchor_rate * n_anchors

        # Cost of all of the mooring lines
        legs_total = n_lines * cost_per_length * L_mooring

        # Total summations
        outputs["mooring_cost"] = legs_total + anchor_total
        outputs["line_mass"] = wet_mass_per_length * L_mooring
        outputs["mooring_mass"] = wet_mass_per_length * L_mooring * n_lines

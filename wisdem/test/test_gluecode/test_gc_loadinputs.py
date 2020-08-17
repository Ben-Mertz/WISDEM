import unittest
import os
import wisdem.glue_code.gc_LoadInputs as gcl

test_dir = os.path.dirname( os.path.dirname( os.path.dirname( os.path.dirname( os.path.realpath(__file__) ) ) ) ) + os.sep + 'examples' + os.sep + 'reference_turbines_lcoe' + os.sep

class TestLoadInputs(unittest.TestCase):
    def setUp(self):
        fname_wt_input         = test_dir + 'nrel5mw.yaml'
        fname_modeling_options = test_dir + 'modeling_options.yaml'
        fname_analysis_options = test_dir + 'analysis_options.yaml'

        self.myobj = gcl.WindTurbineOntologyPython(fname_wt_input, fname_modeling_options, fname_analysis_options)
        
    def testRunFlags(self):
        self.myobj.defaults['test_absent1'] = {}
        self.myobj.defaults['test_present1'] = {}
        self.myobj.defaults['components']['test_absent2'] = {}
        self.myobj.defaults['components']['test_present2'] = {}

        self.myobj.wt_init['test_present1'] = {}
        self.myobj.wt_init['components']['test_present2'] = {}
        self.myobj.set_run_flags()
        self.assertTrue(self.myobj.modeling_options['flags']['test_present1'])
        self.assertTrue(self.myobj.modeling_options['flags']['test_present2'])
        self.assertFalse(self.myobj.modeling_options['flags']['test_absent1'])
        self.assertFalse(self.myobj.modeling_options['flags']['test_absent2'])
    
    def testOptFlags(self):
        self.myobj.analysis_options['optimization_variables']['test1'] = {}
        self.myobj.analysis_options['optimization_variables']['test1']['flag'] = False
        self.myobj.analysis_options['optimization_variables']['test1']['test2'] = {}
        self.myobj.analysis_options['optimization_variables']['test1']['test2']['flag'] = False
        self.myobj.analysis_options['optimization_variables']['test1']['test2']['test3'] = {}
        self.myobj.analysis_options['optimization_variables']['test1']['test2']['test3']['flag'] = False

        self.myobj.set_opt_flags()
        self.assertFalse(self.myobj.analysis_options['opt_flag'])

        self.myobj.analysis_options['optimization_variables']['test1']['flag'] = True
        self.myobj.set_opt_flags()
        self.assertTrue(self.myobj.analysis_options['opt_flag'])

        self.myobj.analysis_options['optimization_variables']['test1']['flag'] = False
        self.myobj.analysis_options['optimization_variables']['test1']['test2']['test3']['flag'] = True
        self.myobj.set_opt_flags()
        self.assertTrue(self.myobj.analysis_options['opt_flag'])

        self.myobj.analysis_options['optimization_variables']['blade']['aero_shape']['twist']['n_opt'] = 500
        self.myobj.analysis_options['optimization_variables']['blade']['aero_shape']['chord']['n_opt'] = 600
        self.myobj.analysis_options['optimization_variables']['blade']['structure']['spar_cap_ss']['n_opt'] = 700
        self.myobj.analysis_options['optimization_variables']['blade']['structure']['spar_cap_ps']['n_opt'] = 800
        self.myobj.set_opt_flags()
        self.assertEqual(self.myobj.analysis_options['optimization_variables']['blade']['aero_shape']['twist']['n_opt'],
                         self.myobj.modeling_options['rotorse']['n_span'])
        self.assertEqual(self.myobj.analysis_options['optimization_variables']['blade']['aero_shape']['chord']['n_opt'],
                         self.myobj.modeling_options['rotorse']['n_span'])
        self.assertEqual(self.myobj.analysis_options['optimization_variables']['blade']['structure']['spar_cap_ss']['n_opt'],
                         self.myobj.modeling_options['rotorse']['n_span'])
        self.assertEqual(self.myobj.analysis_options['optimization_variables']['blade']['structure']['spar_cap_ps']['n_opt'],
                         self.myobj.modeling_options['rotorse']['n_span'])

        
def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestLoadInputs))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner().run(suite())

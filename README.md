# PReLIM-imputation
### Get PReLIM imputed matrices (Reads x CpGs) for each bin given the bin size, chromosome &amp; input BAM file.

### Notes on prerequisites when installing/ running CluBCPG/ PReLIM

1) There were some issues (when installing) if conda virtual environments were used for the CluBCPG/PReLIM packages. So, use `virtualenv` to create the virtual environment.

   Installing → `pip3 install virtualenv`\
   Creating venv → `virtualenv ~/venv/clubcpg -p python3`\
   Activating → `source ~/venv/clubcpg/bin/activate` <br />
    <br />
2) When installing CluBCPG using `pip install clubcpg` there were few errors.

 - Install `Cython`, `pysam==0.15.2`, `setuptools==58` manually using `pip`.
 - Although in the installation guide it’s mentioned that `numpy==1.16.5` is required,  upgrade numpy for it to work (`pip install --upgrade numpy`). The error given before upgrading was `sklearn ValueError: numpy.ndarray size changed, may indicate binary incompatibility. Expected 96 from C header, got 80 from PyObject.`

3) When running the tests there was an issue with the pysam module  `ModuleNotFoundError: No module named 'utils’`. To fix this issue, I had to change the file in the location `/venv/clubcpg/lib/python3.8/site-packages/pysam/samtools.py`.The following change was done in the first line to fix the import:\
`from pysam.utils import PysamDispatcher`


### Getting Imputed Matrices 

 - **Inputs :** input BAM file (can be a BAM file with one chromosome, after splitting), Bin Size, Chromosome, Output Directory
 - **Outputs :** 
   - Text files containing original extracted matrices for each available bin & text files each containing matrices after imputing process for CpG densities 2,3,4 & 5 for each available bin.
   - `.npy` files containing python dictionary of original extracted matrices for each available bin & `.npy` files each containing python dictionaries of matrices after imputing process for CpG densities 2,3,4 & 5 for each available bin. `.npy` files will be useful if you intend to use the matrices for downstream analyses. Following code snippet can be used to retrieve dictionaries from the `.npy` files.
 ```python
import numpy as np
data = np.load('path/your_file.npy')
dictionary_of_matrices = data[()]
```
   
**NOTE: Available bin --> Any bun with atleast one read.**

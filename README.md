# ARQ: Experiment Runner

**ARQ** is a framework for creating cryptographic schemes
that handle aggregate range queries (sum, minimum, median, and mode) over
encrypted datasets. Using **ARQ**, structures from the plaintext data
management community may be easily unified with existing
*structured encryption* primitives to produce schemes with defined, provable
leakage profiles and security guarantees.

This repository is the associated artifact landing page for the paper "Time- and
Space-Efficient Range Aggregate Queries over Encrypted Databases" by Zachary
Espiritu, Evangelia Anna Markatou, and Roberto Tamassia.
Our paper provides
more details on the benefits of the **ARQ** framework in comparison to prior
work, as well as formal leakage definitions and adaptive security proofs. Our
paper's artifacts consist of:

* This repository, which contains our experiment runner and datasets (where legally
    reproducible).
* The [Arca][Arca] repository, which contains the implementation for the `arca`
    library containing several implementations of encrypted search algorithms
    (including the implementation of the **ARQ** framework and the plaintext
    schemes used to instantiate it).

## Usage

If you have access to a Slurm cluster, simply submit the scripts in the `slurm` folder
via the `sbatch` command. Example:

```bash
sbatch slurm/all-gowalla.sh # runs the Gowalla experiments
```

You can also run the benchmark script locally (though you may be memory-limited). For
example, the following command runs the `MinimumLinearEMT` scheme against the
`data/amazon-books.csv` dataset:

```bash
python src/experiment.py -s MinimumLinearEMT \
                         -n localhost -p 8000 \
                         -q all \
                         -o output.csv \
                         --debug \
                         --num_processes 8 \
                         --dataset data/amazon-books.csv
```

Similarly, this command runs the `MedianAlphaApprox` scheme against the
`data/amazon-books.csv` dataset with `alpha` set to `0.5`:

```bash
python src/experiment.py -s MedianAlphaApprox:0.5 \
                         -n localhost -p 8000 \
                         -q all \
                         -o output.csv \
                         --debug \
                         --num_processes 8 \
                         --dataset data/amazon-books.csv
```

You can also have the script generate synthetic datasets of a particular domain size
and density, which may be useful if you need to run the script on a memory-constrained
machine.

- The `--synthetic_domain_size` sets how large the domain is (in the example below,
there will be 100 points in the domain). The

- The `--synthetic_sparsity_percent` is a number from 0 to 100 that sets what percentage
of domain points have a filled in point.

For example:

```bash
python src/experiment.py -s MinimumSparseTable \
                         -n localhost -p 8000 \
                         -q all \
                         -o output.csv \
                         --debug \
                         --num_processes 8 \
                         --synthetic_domain_size 100 \
                        --synthetic_sparsity_percent 100
```

[Arca]: https://github.com/cloudsecuritygroup/arca
